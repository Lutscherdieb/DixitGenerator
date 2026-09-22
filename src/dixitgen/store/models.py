"""The card library's tables.

Two things shape this schema.

**Image bytes live in the row, never a path.** The sibling project
`CardGenerator` learned this expensively: artwork addressed by a path had two
writers -- an editable form field and the upload handler -- and saving after an
upload silently restored the old path, discarding the image just uploaded.
Bytes have exactly one writer, and the database file becomes the whole library.

**Backs are their own table, not a flag on ``cards``.** A back is not a
playable card: it has no tags, no notes, and must never appear in the overview
you batch-select from. A ``kind`` column would make that a filter every query
has to remember; a separate table makes it structural.

The two share their image columns through ``ImageMixin`` rather than by
duplication, so a column added to one is added to both.
"""

from __future__ import annotations

import datetime as _dt
from typing import List

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


class Base(DeclarativeBase):
    pass


class ImageMixin:
    """Everything needed to store one uploaded picture and place it on a card."""

    #: The upload, byte for byte as it arrived.  Never re-encoded: the crop
    #: happens at export time from these bytes, so re-nudging the focus a
    #: hundred times costs nothing in quality.
    image: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    image_mime: Mapped[str] = mapped_column(String(64), nullable=False, default="image/png")

    #: Source pixel size, cached on upload.  The overview flags soft art with
    #: these instead of decoding every image in the library to draw one grid.
    src_w: Mapped[int] = mapped_column(Integer, nullable=False)
    src_h: Mapped[int] = mapped_column(Integer, nullable=False)

    #: The crop nudge: a point in 0..1 of the source that the crop window
    #: centres on, y from the top.  Two numbers rather than a pixel rectangle,
    #: so it survives a re-upload at a different resolution.
    focus_x: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    focus_y: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)

    #: A small JPEG for the grid, cropped to the card's shape so a tile shows
    #: what will actually print.  Regenerated whenever the focus changes.
    thumb: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    #: Content hash of ``image``.  Advisory only -- deliberately NOT unique,
    #: because re-using one picture for two cards is a legitimate thing to do.
    #: It exists so an upload can say "this is already in your library"
    #: without a full-table byte comparison.
    image_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    @property
    def focus(self) -> tuple:
        return (self.focus_x, self.focus_y)


card_tags = Table(
    "card_tags",
    Base.metadata,
    Column("card_id", ForeignKey("cards.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(Base):
    """A free-form label. Normalised on the way in -- see ``repo.normalise_tag``."""

    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("name", name="uq_tags_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)

    cards: Mapped[List["Card"]] = relationship(
        secondary=card_tags, back_populates="tags"
    )

    def __repr__(self) -> str:
        return "Tag({!r})".format(self.name)


class Card(Base, ImageMixin):
    """One playable card. The image is the card; nothing here ever prints on it."""

    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    notes: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_at: Mapped[_dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now
    )

    tags: Mapped[List[Tag]] = relationship(
        secondary=card_tags, back_populates="cards", lazy="selectin"
    )

    def __repr__(self) -> str:
        return "Card(id={}, name={!r})".format(self.id, self.name)


class Back(Base, ImageMixin):
    """A back design. Applies to a whole exported batch, never to one card."""

    __tablename__ = "backs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_at: Mapped[_dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[_dt.datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now
    )

    def __repr__(self) -> str:
        return "Back(id={}, name={!r})".format(self.id, self.name)
