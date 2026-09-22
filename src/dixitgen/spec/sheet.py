"""Sheet layout -- where a card lands on the paper, and where its back lands.

Coordinate convention
---------------------
Millimetres, **origin bottom-left, y increasing upward** -- PDF user space, so
a coordinate handed to reportlab needs a unit conversion and nothing else.
Grid slots, by contrast, are named in reading order: ``row=0`` is the **top**
row, because that is how a person looks at a sheet.  ``card_box`` is the one
place those two conventions meet.

Why the cards touch
-------------------
Adjacent cards share a cut line, so one guillotine pass serves two cards and a
cut that lands a millimetre off still leaves both cards full-bleed -- one comes
out 81 mm, its neighbour 79 mm, and neither shows a white edge.  A gutter
between cards would turn the same error into a white sliver, which is the
failure people actually notice on a laminated card.

The block's **outer** edges have no neighbour to borrow from, so the art there
is grown outward by ``outer_bleed_mm`` instead (see ``art_box``).

Why the block is centred
------------------------
Duplex registration falls out of the centring for free.  With the block
centred, the mirror of a front slot about the page's centre line *is* another
slot of the same grid, exactly -- see ``back_slot``, and the proof asserted by
``verify.assert_registration``.  Move the block off-centre and every back needs
a measured offset instead.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
from typing import Iterator, List, Tuple

from .card import DIXIT, CardFormat
from .units import MM_TOLERANCE, mm_to_pt


class Flip(str, Enum):
    """How the paper turns over between the front pass and the back pass.

    The value is what an export writes into a filename and an API payload, so
    it is a stable string, not an auto number.
    """

    #: Automatic duplex, long-edge binding -- the usual home-printer default.
    #: For portrait paper the sheet turns about its vertical edge, so the back
    #: is mirrored left-to-right.
    LONG_EDGE = "long-edge"

    #: Automatic duplex, short-edge binding.  The sheet turns about its
    #: horizontal edge, so the back is mirrored top-to-bottom *and* the back
    #: image is rotated 180 degrees -- otherwise a cut card flipped the natural
    #: way (left-to-right) shows its back upside down.
    SHORT_EDGE = "short-edge"

    #: Two files, fed by hand.  Assumes the stack goes back in the same way up,
    #: which is geometrically the long-edge case.
    MANUAL = "manual"


@dataclass(frozen=True)
class Rect:
    """An axis-aligned rectangle in millimetres, origin bottom-left."""

    x_mm: float
    y_mm: float
    w_mm: float
    h_mm: float

    @property
    def right_mm(self) -> float:
        return self.x_mm + self.w_mm

    @property
    def top_mm(self) -> float:
        return self.y_mm + self.h_mm

    def as_tuple(self) -> Tuple[float, float, float, float]:
        """``(x, y, width, height)`` in millimetres -- the form assertions compare."""
        return (self.x_mm, self.y_mm, self.w_mm, self.h_mm)

    def as_pt(self) -> Tuple[float, float, float, float]:
        """``(x, y, width, height)`` in PDF points, ready for reportlab."""
        return (
            mm_to_pt(self.x_mm),
            mm_to_pt(self.y_mm),
            mm_to_pt(self.w_mm),
            mm_to_pt(self.h_mm),
        )

    def grown(
        self,
        left: float = 0.0,
        bottom: float = 0.0,
        right: float = 0.0,
        top: float = 0.0,
    ) -> "Rect":
        """A copy pushed outward by the given millimetres on each named side."""
        return Rect(
            x_mm=self.x_mm - left,
            y_mm=self.y_mm - bottom,
            w_mm=self.w_mm + left + right,
            h_mm=self.h_mm + bottom + top,
        )

    def overlaps(self, other: "Rect", tol: float = MM_TOLERANCE) -> bool:
        """True if the two rectangles share more than ``tol`` of area.

        Touching edges are not an overlap: adjacent cards share a cut line by
        design, and a crop mark that stops exactly on a card's edge has not
        entered it.
        """
        return (
            self.x_mm < other.right_mm - tol
            and other.x_mm < self.right_mm - tol
            and self.y_mm < other.top_mm - tol
            and other.y_mm < self.top_mm - tol
        )


@dataclass(frozen=True)
class Segment:
    """A straight line drawn on the sheet, in millimetres.  Crop marks are these."""

    x1_mm: float
    y1_mm: float
    x2_mm: float
    y2_mm: float

    @property
    def bbox(self) -> Rect:
        x = min(self.x1_mm, self.x2_mm)
        y = min(self.y1_mm, self.y2_mm)
        return Rect(x, y, abs(self.x2_mm - self.x1_mm), abs(self.y2_mm - self.y1_mm))

    def as_pt(self) -> Tuple[float, float, float, float]:
        """``(x1, y1, x2, y2)`` in PDF points."""
        return (
            mm_to_pt(self.x1_mm),
            mm_to_pt(self.y1_mm),
            mm_to_pt(self.x2_mm),
            mm_to_pt(self.y2_mm),
        )


@dataclass(frozen=True)
class PaperSize:
    id: str
    label: str
    w_mm: float
    h_mm: float

    @property
    def w_pt(self) -> float:
        return mm_to_pt(self.w_mm)

    @property
    def h_pt(self) -> float:
        return mm_to_pt(self.h_mm)


#: ISO 216.  A4 is 210 x 297 mm -- see the ``paper-and-pdf-units`` reference.
A4 = PaperSize(id="a4", label="A4 (210 x 297 mm)", w_mm=210.0, h_mm=297.0)

PAPER_SIZES = {A4.id: A4}


@dataclass(frozen=True)
class SheetLayout:
    """One paper size, one card format, and the grid of cards on it."""

    paper: PaperSize = A4
    card: CardFormat = DIXIT
    cols: int = 2
    rows: int = 2

    #: Art grown outward past the block's outer edges, so a cut that lands
    #: outside the block still hits art instead of paper.
    outer_bleed_mm: float = 3.0

    #: Crop-mark geometry.  ``mark_gap_mm`` is measured from the outer edge of
    #: the bled art, not from the card, so a mark can never touch artwork.
    mark_len_mm: float = 4.0
    mark_gap_mm: float = 1.5

    #: What a consumer printer cannot reach.  Marks must stay inside this.
    unprintable_margin_mm: float = 5.0

    def __post_init__(self) -> None:
        if self.cols < 1 or self.rows < 1:
            raise ValueError(
                "sheet layout: grid must be at least 1x1, got {}x{}".format(
                    self.cols, self.rows
                )
            )
        self.validate()

    # -- the block ---------------------------------------------------------
    @property
    def block_w_mm(self) -> float:
        return self.cols * self.card.trim_w_mm

    @property
    def block_h_mm(self) -> float:
        return self.rows * self.card.trim_h_mm

    @property
    def margin_x_mm(self) -> float:
        """Paper left of the block.  Equal on both sides -- the block is centred."""
        return (self.paper.w_mm - self.block_w_mm) / 2.0

    @property
    def margin_y_mm(self) -> float:
        return (self.paper.h_mm - self.block_h_mm) / 2.0

    @property
    def cards_per_sheet(self) -> int:
        return self.cols * self.rows

    @property
    def furniture_reach_mm(self) -> float:
        """How far past the block the outermost drawn element reaches."""
        return self.outer_bleed_mm + self.mark_gap_mm + self.mark_len_mm

    # -- slots -------------------------------------------------------------
    def slots(self) -> Iterator[Tuple[int, int]]:
        """Every ``(row, col)`` in reading order: left to right, top to bottom."""
        for row in range(self.rows):
            for col in range(self.cols):
                yield (row, col)

    def _check_slot(self, row: int, col: int) -> None:
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            raise IndexError(
                "slot ({}, {}) is outside a {}x{} grid".format(
                    row, col, self.rows, self.cols
                )
            )

    def card_box(self, row: int, col: int) -> Rect:
        """The finished card at grid slot ``(row, col)``; ``row=0`` is the top row.

        This is the cut line.  Nothing but that card's own art may enter it.
        """
        self._check_slot(row, col)
        return Rect(
            x_mm=self.margin_x_mm + col * self.card.trim_w_mm,
            # row 0 is the top row, but y grows upward from the bottom.
            y_mm=self.paper.h_mm - self.margin_y_mm - (row + 1) * self.card.trim_h_mm,
            w_mm=self.card.trim_w_mm,
            h_mm=self.card.trim_h_mm,
        )

    def art_box(self, row: int, col: int) -> Rect:
        """Where this slot's image is actually drawn.

        Equal to ``card_box`` on every side that has a neighbour, and grown by
        ``outer_bleed_mm`` on every side sitting on the block's outer edge.
        Art drawn past a shared edge would print on the neighbouring card.
        """
        box = self.card_box(row, col)
        bleed = self.outer_bleed_mm
        return box.grown(
            left=bleed if col == 0 else 0.0,
            right=bleed if col == self.cols - 1 else 0.0,
            top=bleed if row == 0 else 0.0,
            bottom=bleed if row == self.rows - 1 else 0.0,
        )

    # -- duplex ------------------------------------------------------------
    def back_slot(self, row: int, col: int, flip: Flip) -> Tuple[int, int]:
        """The slot on the *back* page that lands behind front slot ``(row, col)``.

        Long-edge and manual mirror the columns; short-edge mirrors the rows.
        The mapping is its own inverse, which ``verify.assert_registration``
        asserts -- a mapping that is not an involution cannot describe turning
        a sheet over.
        """
        self._check_slot(row, col)
        if flip in (Flip.LONG_EDGE, Flip.MANUAL):
            return (row, self.cols - 1 - col)
        if flip is Flip.SHORT_EDGE:
            return (self.rows - 1 - row, col)
        raise ValueError("unknown flip {!r}".format(flip))

    @staticmethod
    def back_rotation_deg(flip: Flip) -> int:
        """How far to rotate the back image so a cut card reads upright.

        A person flips a card about its vertical axis.  Under short-edge duplex
        the back arrives mirrored top-to-bottom, so the image needs 180 degrees
        to come back the right way up.
        """
        return 180 if flip is Flip.SHORT_EDGE else 0

    # -- crop marks --------------------------------------------------------
    def crop_marks(self) -> List[Segment]:
        """Short lines in the paper margin, on the extension of every cut line.

        Never inside a card box, and never inside the bled art: they start
        ``mark_gap_mm`` beyond the art's outer edge.  ``verify.assert_clean_cards``
        is what actually holds that promise.
        """
        marks: List[Segment] = []
        left = self.margin_x_mm
        right = self.margin_x_mm + self.block_w_mm
        bottom = self.margin_y_mm
        top = self.margin_y_mm + self.block_h_mm
        out = self.outer_bleed_mm + self.mark_gap_mm

        # Vertical cut lines, marked above and below the block.
        for i in range(self.cols + 1):
            x = left + i * self.card.trim_w_mm
            marks.append(Segment(x, top + out, x, top + out + self.mark_len_mm))
            marks.append(Segment(x, bottom - out, x, bottom - out - self.mark_len_mm))

        # Horizontal cut lines, marked left and right of the block.
        for i in range(self.rows + 1):
            y = bottom + i * self.card.trim_h_mm
            marks.append(Segment(left - out, y, left - out - self.mark_len_mm, y))
            marks.append(Segment(right + out, y, right + out + self.mark_len_mm, y))

        return marks

    # -- validation --------------------------------------------------------
    def validate(self) -> None:
        """Raise unless the grid, its bleed and its marks all fit the paper."""
        if self.block_w_mm > self.paper.w_mm or self.block_h_mm > self.paper.h_mm:
            raise ValueError(
                "sheet layout: {}x{} cards of {}x{}mm ({}x{}mm) do not fit {} "
                "({}x{}mm)".format(
                    self.cols,
                    self.rows,
                    self.card.trim_w_mm,
                    self.card.trim_h_mm,
                    self.block_w_mm,
                    self.block_h_mm,
                    self.paper.label,
                    self.paper.w_mm,
                    self.paper.h_mm,
                )
            )
        reach = self.furniture_reach_mm
        for axis, margin in (
            ("horizontal", self.margin_x_mm),
            ("vertical", self.margin_y_mm),
        ):
            if margin < reach + self.unprintable_margin_mm:
                raise ValueError(
                    "sheet layout: {} margin is {:.2f}mm, but drawn furniture "
                    "reaches {:.2f}mm past the block and the outer {:.2f}mm of "
                    "paper is unprintable".format(
                        axis, margin, reach, self.unprintable_margin_mm
                    )
                )

    @classmethod
    def fit(cls, paper: PaperSize = A4, card: CardFormat = DIXIT, **kw) -> "SheetLayout":
        """The largest centred grid of ``card`` that ``paper`` holds.

        Derives ``cols``/``rows`` rather than taking them on trust, so a new
        paper size or card format is a data change, not a code change.  The
        margin each side has to hold the bleed, the crop-mark gap, the mark
        itself and the printer's unreachable edge, so that sum is what comes
        off the usable width -- not the card size alone.
        """
        defaults = {f.name: f.default for f in fields(cls)}
        setting = lambda name: kw.get(name, defaults[name])  # noqa: E731
        reach = (
            setting("outer_bleed_mm")
            + setting("mark_gap_mm")
            + setting("mark_len_mm")
            + setting("unprintable_margin_mm")
        )
        cols = int((paper.w_mm - 2 * reach) // card.trim_w_mm)
        rows = int((paper.h_mm - 2 * reach) // card.trim_h_mm)
        if cols < 1 or rows < 1:
            raise ValueError(
                "no {}x{}mm card fits {} once {:.2f}mm of bleed, crop marks and "
                "unprintable edge are allowed for on each side".format(
                    card.trim_w_mm, card.trim_h_mm, paper.label, reach
                )
            )
        return cls(paper=paper, card=card, cols=cols, rows=rows, **kw)


#: What an export uses unless the caller says otherwise.
SHEET = SheetLayout.fit()
