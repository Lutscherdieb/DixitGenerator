"""Every read and write of the card library goes through this module.

Two invariants it exists to hold:

* **A card's derived fields are never written by hand.** ``src_w``/``src_h``,
  ``thumb`` and ``image_sha256`` are computed from the bytes on the way in, and
  the thumbnail is regenerated whenever the focus changes. A caller that sets a
  focus directly on the model would leave the tile showing the old crop.
* **Tags are normalised once, here.** ``"Surreal"``, ``" surreal "`` and
  ``"SURREAL"`` are the same tag, or filtering quietly splits a deck in two.
"""

from __future__ import annotations

import hashlib
import io
from typing import Iterable, List, Optional, Sequence, Tuple

from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..export.sheet_pdf import CardArt
from ..render.thumb import make_thumb
from .models import Back, Card, Tag

#: What PIL's format name means as a MIME type. Anything else falls back to
#: the generic binary type rather than guessing.
MIME_BY_FORMAT = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
    "GIF": "image/gif",
    "BMP": "image/bmp",
    "TIFF": "image/tiff",
}


class StoreError(RuntimeError):
    """A request the library cannot satisfy -- a bad image, a missing row."""


# ---------------------------------------------------------------------------
# tags
# ---------------------------------------------------------------------------


def normalise_tag(name: str) -> str:
    """Trim, collapse inner whitespace, lowercase.

    One spelling per tag. Without this, ``"deck 1"`` and ``"Deck  1"`` are two
    tags and "select everything in deck 1" silently returns half the deck.
    """
    return " ".join(name.split()).lower()


def get_or_create_tag(session: Session, name: str) -> Tag:
    normalised = normalise_tag(name)
    if not normalised:
        raise StoreError("a tag cannot be empty or whitespace only")
    existing = session.scalar(select(Tag).where(Tag.name == normalised))
    if existing is not None:
        return existing
    tag = Tag(name=normalised)
    session.add(tag)
    session.flush()
    return tag


def set_tags(session: Session, card: Card, names: Iterable[str]) -> Card:
    """Replace a card's tags with ``names`` (normalised and de-duplicated)."""
    wanted: List[str] = []
    for name in names:
        normalised = normalise_tag(name)
        if normalised and normalised not in wanted:
            wanted.append(normalised)
    card.tags = [get_or_create_tag(session, name) for name in wanted]
    session.flush()
    return card


def all_tags(session: Session) -> List[Tuple[str, int]]:
    """``[(name, how many cards carry it)]``, most used first then alphabetical.

    Tags with no cards left are included with a count of 0 rather than hidden:
    a tag that vanishes the moment its last card is deleted looks like data
    loss. ``prune_unused_tags`` removes them when you actually want that.
    """
    rows = session.execute(
        select(Tag.name, func.count(Card.id))
        .select_from(Tag)
        .outerjoin(Tag.cards)
        .group_by(Tag.id)
        .order_by(func.count(Card.id).desc(), Tag.name)
    ).all()
    return [(name, count) for name, count in rows]


def prune_unused_tags(session: Session) -> int:
    """Delete tags no card carries. Returns how many went."""
    orphans = [tag for tag in session.scalars(select(Tag)).all() if not tag.cards]
    for tag in orphans:
        session.delete(tag)
    session.flush()
    return len(orphans)


# ---------------------------------------------------------------------------
# images
# ---------------------------------------------------------------------------


def inspect_image(data: bytes) -> Tuple[int, int, str]:
    """``(width, height, mime)`` of an upload, or raise ``StoreError``.

    Rejecting a bad upload here, rather than at export time, is deliberate: a
    file that is not an image should fail while you are looking at the upload,
    not three weeks later in the middle of a print run.
    """
    if not data:
        raise StoreError("the upload is empty")
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
        with Image.open(io.BytesIO(data)) as img:
            width, height = img.size
            fmt = (img.format or "").upper()
    except Exception as exc:  # PIL raises a wide variety for a bad file
        raise StoreError("not a readable image: {}".format(exc)) from exc
    return width, height, MIME_BY_FORMAT.get(fmt, "application/octet-stream")


def _apply_image(row, data: bytes, focus: Tuple[float, float]) -> None:
    """Fill every derived field from the bytes. The one writer of all of them."""
    width, height, mime = inspect_image(data)
    with Image.open(io.BytesIO(data)) as img:
        img.load()
        row.thumb = make_thumb(img, focus)
    row.image = data
    row.image_mime = mime
    row.src_w = width
    row.src_h = height
    row.focus_x, row.focus_y = _clamp_focus(focus)
    row.image_sha256 = hashlib.sha256(data).hexdigest()


def _clamp_focus(focus: Tuple[float, float]) -> Tuple[float, float]:
    return (
        min(max(float(focus[0]), 0.0), 1.0),
        min(max(float(focus[1]), 0.0), 1.0),
    )


def find_by_content(session: Session, data: bytes) -> List[Card]:
    """Cards already holding these exact bytes -- advisory duplicate detection.

    Not a constraint: using one picture for two cards is legitimate. This just
    lets an upload say "you already have this".
    """
    digest = hashlib.sha256(data).hexdigest()
    return list(session.scalars(select(Card).where(Card.image_sha256 == digest)).all())


# ---------------------------------------------------------------------------
# cards
# ---------------------------------------------------------------------------


def add_card(
    session: Session,
    image: bytes,
    name: str = "",
    notes: str = "",
    tags: Sequence[str] = (),
    focus: Tuple[float, float] = (0.5, 0.5),
) -> Card:
    card = Card(name=name.strip(), notes=notes)
    _apply_image(card, image, focus)
    session.add(card)
    session.flush()
    if tags:
        set_tags(session, card, tags)
    return card


def get_card(session: Session, card_id: int) -> Card:
    card = session.get(Card, card_id)
    if card is None:
        raise StoreError("no card with id {}".format(card_id))
    return card


def list_cards(
    session: Session,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    ids: Optional[Sequence[int]] = None,
) -> List[Card]:
    """Cards, newest first, optionally filtered.

    ``ids`` preserves the **caller's** order, because an export batch is a
    selection in the order the user made it, not in database order.
    """
    if ids is not None:
        found = {
            card.id: card
            for card in session.scalars(select(Card).where(Card.id.in_(list(ids)))).all()
        }
        missing = [i for i in ids if i not in found]
        if missing:
            raise StoreError("no card with id {}".format(missing[0]))
        return [found[i] for i in ids]

    query = select(Card)
    if tag:
        query = query.join(Card.tags).where(Tag.name == normalise_tag(tag))
    if search:
        needle = "%{}%".format(search.strip().lower())
        query = query.where(
            func.lower(Card.name).like(needle) | func.lower(Card.notes).like(needle)
        )
    query = query.order_by(Card.created_at.desc(), Card.id.desc())
    return list(session.scalars(query).unique().all())


def update_card(
    session: Session,
    card_id: int,
    name: Optional[str] = None,
    notes: Optional[str] = None,
    tags: Optional[Sequence[str]] = None,
) -> Card:
    card = get_card(session, card_id)
    if name is not None:
        card.name = name.strip()
    if notes is not None:
        card.notes = notes
    if tags is not None:
        set_tags(session, card, tags)
    session.flush()
    return card


def set_focus(session: Session, card_id: int, focus: Tuple[float, float]) -> Card:
    """Move the crop window, and regenerate the tile so the grid agrees.

    Regenerating is the whole reason this is a function rather than a field
    assignment: a focus changed without a new thumbnail leaves the overview
    showing a crop the PDF will not produce.
    """
    card = get_card(session, card_id)
    card.focus_x, card.focus_y = _clamp_focus(focus)
    with Image.open(io.BytesIO(card.image)) as img:
        img.load()
        card.thumb = make_thumb(img, card.focus)
    session.flush()
    return card


def replace_image(session: Session, card_id: int, image: bytes) -> Card:
    """Swap the artwork, keeping the name, notes, tags and crop focus."""
    card = get_card(session, card_id)
    _apply_image(card, image, card.focus)
    session.flush()
    return card


def delete_card(session: Session, card_id: int) -> None:
    """Permanent. The database holds the only copy of the image bytes.

    Hard delete is the author's decision (2026-09-22); the confirmation lives
    in the UI, and `data/cards.db` is the file to back up.
    """
    card = get_card(session, card_id)
    session.delete(card)
    session.flush()


# ---------------------------------------------------------------------------
# backs
# ---------------------------------------------------------------------------


def add_back(
    session: Session,
    image: bytes,
    name: str = "",
    focus: Tuple[float, float] = (0.5, 0.5),
) -> Back:
    back = Back(name=name.strip())
    _apply_image(back, image, focus)
    session.add(back)
    session.flush()
    return back


def get_back(session: Session, back_id: int) -> Back:
    back = session.get(Back, back_id)
    if back is None:
        raise StoreError("no back with id {}".format(back_id))
    return back


def list_backs(session: Session) -> List[Back]:
    return list(
        session.scalars(
            select(Back).order_by(Back.created_at.desc(), Back.id.desc())
        ).all()
    )


def delete_back(session: Session, back_id: int) -> None:
    session.delete(get_back(session, back_id))
    session.flush()


# ---------------------------------------------------------------------------
# the bridge to the export
# ---------------------------------------------------------------------------


def to_card_art(card: Card) -> CardArt:
    """Turn a stored row into what ``export_batch`` takes.

    The stored bytes are opened as-is -- no re-encode, no resize. Whatever
    resolution was uploaded is the resolution that reaches the PDF.
    """
    img = Image.open(io.BytesIO(card.image))
    img.load()
    return CardArt(
        name=card.name or "card-{}".format(card.id),
        image=img,
        focus=card.focus,
    )


def to_back_image(back: Back) -> Image.Image:
    img = Image.open(io.BytesIO(back.image))
    img.load()
    return img


def batch_for_export(
    session: Session, card_ids: Sequence[int]
) -> List[CardArt]:
    """The selection, in the order it was made, ready for ``export_batch``."""
    return [to_card_art(card) for card in list_cards(session, ids=card_ids)]
