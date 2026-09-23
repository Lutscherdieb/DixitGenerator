"""Batch -> per-card image files, zipped.  The non-sheet half of the export.

Two outputs share this writer, and **both start from the same crop**:

    crops      the card's trim crop -- exactly what the overview tile shows and
               exactly what a cut A4 card shows.
    mpc-dixit  that same trim crop with the press's bleed added outside it.

One framing, three outputs
--------------------------
The trim crop is the single source of framing for the sheet PDF, the plain
images and the press files alike.  A card therefore shows the same slice of its
source wherever it comes out, which is the property the author asked for on
2026-09-23 after seeing the first version deviate.

The rejected alternative is worth keeping: cropping the source to the *bled*
rectangle is one line shorter and makes the press card a tighter crop than the
sheet card, because adding equal bleed to a non-square changes its aspect.  See
``crop_with_full_bleed`` and ``dixitgen.spec.press``.

Nothing is resampled either way.  The crop is taken at the source's own
resolution and written as-is -- the same promise the PDF path makes -- so a
4000 px source reaches the file as 4000 px and file sizes differ per card.
That is correct: the alternative is inventing pixels for a small source and
discarding them for a large one.

Why a zip
---------
Eighty cards is eighty files.  The browser can only usefully be handed one
thing to download, and a directory of loose PNGs in ``out/`` would be
indistinguishable from the last batch's.  One archive per export, named after
the batch, is the whole story.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from PIL import Image

from ..render.crop import crop_to_fill, crop_with_full_bleed
from ..spec.sheet import Rect
from ..spec.verify import art_warnings
from .formats import OutputOption
from .sheet_pdf import CardArt, ExportResult

#: A card name becomes a filename; anything outside this is collapsed.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")

#: What the back is written as when one is chosen.  A single shared back is
#: what a press's "same back for every card" flow takes, and what this
#: project's backs shelf models -- one back per batch, not one per card.
BACK_STEM = "back"


def _slug(name: str, fallback: str) -> str:
    out = _UNSAFE.sub("-", (name or "").strip()).strip("-.")
    return out or fallback


def _flatten(img: Image.Image) -> Image.Image:
    """An opaque RGB copy.

    A printed card has no transparency, and a palette or alpha PNG handed to a
    press is a support email.  Alpha is composited onto white rather than
    dropped, so a part-transparent source degrades to what it would look like
    on paper instead of to black.
    """
    if img.mode == "RGB":
        return img
    if img.mode in ("RGBA", "LA") or "transparency" in img.info:
        rgba = img.convert("RGBA")
        flat = Image.new("RGB", rgba.size, (255, 255, 255))
        flat.paste(rgba, mask=rgba.split()[-1])
        return flat
    return img.convert("RGB")


def _render(
    img: Image.Image, option: OutputOption, focus: Tuple[float, float]
) -> Image.Image:
    """The image file for one card, cropped for ``option``.

    Both branches crop to the card's **trim**; the press branch then grows that
    crop outward by the bleed.  Neither resamples.
    """
    card = option.card
    if option.press is None:
        return crop_to_fill(img, card.trim_w_mm, card.trim_h_mm, focus)
    return crop_with_full_bleed(
        img, card.trim_w_mm, card.trim_h_mm, option.press.bleed_mm, focus
    ).image


def _judged(option: OutputOption) -> Rect:
    """The box a file's resolution is judged across.

    For a press format that is the bled rectangle, so the advisory threshold
    lands exactly on the service's published minimum upload size; for a plain
    crop it is the card trim.  Both are read off spec objects.
    """
    if option.press is not None:
        return Rect(0.0, 0.0, option.press.bled_w_mm, option.press.bled_h_mm)
    return Rect(0.0, 0.0, option.card.trim_w_mm, option.card.trim_h_mm)


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    _flatten(img).save(buf, format="PNG")
    return buf.getvalue()


def _notes(option: OutputOption, count: int, has_back: bool) -> str:
    """A short readme for a press export, so the right product gets ordered.

    Every figure is read off the spec objects, so this cannot drift from what
    was actually written.
    """
    press = option.press
    lines = [
        "{} -- {} cards exported {}".format(
            press.service, count, "with a shared back" if has_back else "fronts only"
        ),
        "",
        "Card size    : {:.0f} x {:.0f} mm ({} x {} px trim at {} DPI)".format(
            press.card.trim_w_mm,
            press.card.trim_h_mm,
            press.card.trim_w_px,
            press.card.trim_h_px,
            press.card.dpi,
        ),
        "Bleed        : {} px a side, already included in every file".format(
            press.bleed_px
        ),
        "File size    : {} x {} px -- what each image in this archive is".format(
            press.upload_w_px, press.upload_h_px
        ),
        "",
        "Every file here already carries its bleed, so upload them as they are;",
        "do not add bleed again in the designer.",
        "",
        "ORDERING: {:.0f} x {:.0f} mm is NOT one of {}' stock sizes -- their".format(
            press.card.trim_w_mm, press.card.trim_h_mm, press.service
        ),
        "nearest is a tarot card, which is about 10 mm narrower.  This size has",
        "to go through their custom-requirements path and they may decline it.",
        "These files are deliberately cut to the same framing as the project's",
        "A4 sheets, so a card ordered here matches a card cut at home.",
    ]
    if has_back:
        lines += [
            "",
            "{}.png is the shared back -- one file for the whole deck.".format(
                BACK_STEM
            ),
        ]
    return "\n".join(lines) + "\n"


def export_card_images(
    cards: Sequence[CardArt],
    out_path: Path,
    option: OutputOption,
    back: Optional[Image.Image] = None,
    back_focus: Tuple[float, float] = (0.5, 0.5),
    progress: Optional[Callable[[int, int], None]] = None,
) -> ExportResult:
    """Crop every card for ``option`` and write them into one zip.

    ``progress`` is called as ``progress(done, total)`` after each image is
    written, the same unit the sheet exporter counts in -- one drawn card.

    Returns an ``ExportResult`` with ``sheets=0`` and ``flip=None``: there are
    no sheets and no duplex pass, and saying so with ``None`` beats reporting a
    flip mode that was never applied.
    """
    if not cards:
        raise ValueError("export_card_images: nothing selected -- a batch needs a card")
    if option.kind != "images":
        raise ValueError(
            "export_card_images: {!r} writes {}, not images".format(
                option.id, option.kind
            )
        )

    judged = _judged(option)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    total = len(cards) + (1 if back is not None else 0)
    done = 0
    if progress:
        progress(0, total)

    warnings: List[str] = []
    written = 0

    # ZIP_STORED, not DEFLATED: PNG is already compressed, so deflating it
    # again costs seconds on a deck of eighty and saves almost nothing.
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_STORED) as archive:
        for index, card in enumerate(cards, 1):
            rendered = _render(card.image, option, card.focus)
            warnings.extend(
                art_warnings(option.card, [(card.name, *rendered.size)], judged)
            )
            archive.writestr(
                "{:03d}-{}.png".format(index, _slug(card.name, "card")),
                _png_bytes(rendered),
            )
            written += 1
            done += 1
            if progress:
                progress(done, total)

        if back is not None:
            rendered = _render(back, option, back_focus)
            warnings.extend(
                art_warnings(option.card, [(BACK_STEM, *rendered.size)], judged)
            )
            archive.writestr("{}.png".format(BACK_STEM), _png_bytes(rendered))
            written += 1
            done += 1
            if progress:
                progress(done, total)

        if option.press is not None:
            archive.writestr(
                "README-{}.txt".format(option.press.id),
                _notes(option, len(cards), back is not None),
            )

    return ExportResult(
        paths=[out_path],
        sheets=0,
        cards=len(cards),
        flip=None,
        warnings=warnings,
        images=written,
    )
