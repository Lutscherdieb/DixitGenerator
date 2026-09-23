"""Batch -> PDF.  The composition step, and the only writer of print output.

What it produces
----------------
For ``Flip.LONG_EDGE`` and ``Flip.SHORT_EDGE``: one file, pages interleaved
front, back, front, back -- what an automatic-duplex printer expects.

For ``Flip.MANUAL``: two files, ``<name>.fronts.pdf`` and ``<name>.backs.pdf``,
to be fed by hand.

Every placement comes from a ``SheetLayout``.  Nothing in this module computes
a position; it converts the layout's millimetres to points and draws.  The
geometry assertions run **before** the first byte is written, so a batch that
would not register never produces a file to mistake for a good one.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from ..render.crop import crop_with_bleed, rotate_sides
from ..spec.sheet import Flip, SheetLayout
from ..spec.units import mm_to_pt
from ..spec.verify import (
    art_warnings,
    assert_art_inside_own_slot,
    assert_clean_cards,
    assert_registration,
)

#: Crop marks are hairlines.  0.25pt is the thinnest a consumer printer
#: reliably renders; thinner disappears, thicker becomes a cut target of its
#: own width and defeats the point of a mark.
MARK_WIDTH_PT = 0.25


@dataclass(frozen=True)
class CardArt:
    """One card in a batch: an image, a name for messages, and its crop nudge."""

    name: str
    image: Image.Image
    focus: Tuple[float, float] = (0.5, 0.5)


@dataclass(frozen=True)
class ExportResult:
    """What an export produced, for the caller to report to the user.

    Shared with the per-card image writer in ``card_images``, which is why
    ``flip`` is optional and ``sheets`` can be zero: an image export lays
    nothing out on paper and runs no duplex pass, and reporting ``None`` is
    honest where naming a flip mode that was never applied would not be.
    """

    paths: List[Path]
    sheets: int
    cards: int
    flip: Optional[Flip]
    warnings: List[str]
    #: Per-card image files written.  Zero for sheet output, which counts in
    #: sheets instead.
    images: int = 0


def _chunk(items: Sequence[CardArt], size: int) -> List[Sequence[CardArt]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _draw_front_page(
    pdf: canvas.Canvas,
    layout: SheetLayout,
    page_cards: Sequence[CardArt],
    tick: Optional[Callable[[], None]] = None,
) -> List[str]:
    """Draw each card's art so its **trim** region is the preview's crop.

    The card box is the framing; bleed is extra material taken from outside it
    where the source has any.  Drawing to fill the bled box instead would make
    the cut line eat into the picture -- and, since bleed only exists on the
    block's outer edges, by a different amount in every slot.
    """
    warnings: List[str] = []
    slots = list(layout.slots())
    for card, slot in zip(page_cards, slots):
        card_box = layout.card_box(*slot)
        crop = crop_with_bleed(
            card.image,
            layout.card.trim_w_mm,
            layout.card.trim_h_mm,
            card.focus,
            layout.bleed_sides(*slot),
        )
        box = card_box.grown(
            left=crop.left_mm,
            bottom=crop.bottom_mm,
            right=crop.right_mm,
            top=crop.top_mm,
        )
        # Resolution is judged on the trim region, which is what is kept.
        warnings.extend(
            art_warnings(layout.card, [(card.name, *crop.image.size)], box)
        )
        x_pt, y_pt, w_pt, h_pt = box.as_pt()
        pdf.drawImage(ImageReader(crop.image), x_pt, y_pt, width=w_pt, height=h_pt)
        if tick:
            tick()
    _draw_crop_marks(pdf, layout)
    return warnings


def _draw_back_page(
    pdf: canvas.Canvas,
    layout: SheetLayout,
    used_slots: Sequence[Tuple[int, int]],
    back: Image.Image,
    flip: Flip,
    offset_mm: Tuple[float, float],
    back_focus: Tuple[float, float] = (0.5, 0.5),
    tick: Optional[Callable[[], None]] = None,
) -> None:
    """Draw the chosen back into the slot behind each *used* front slot.

    Only the used slots: a part-full last sheet must not print backs behind
    blank paper, or the cut stack gains four sheets of card-shaped nothing.
    """
    rotation = SheetLayout.back_rotation_deg(flip)
    dx_mm, dy_mm = offset_mm
    for slot in used_slots:
        back_slot = layout.back_slot(slot[0], slot[1], flip)
        card_box = layout.card_box(*back_slot)
        wanted = layout.bleed_sides(*back_slot)

        # A 180-degree turn swaps the sides, so the bleed has to be asked for on
        # the opposite ones *before* rotating in order to land correctly after.
        crop = crop_with_bleed(
            back,
            layout.card.trim_w_mm,
            layout.card.trim_h_mm,
            back_focus,
            rotate_sides(wanted) if rotation else wanted,
        )
        art = crop.image.rotate(rotation, expand=True) if rotation else crop.image
        got = rotate_sides(crop.sides) if rotation else crop.sides

        box = card_box.grown(left=got[0], bottom=got[1], right=got[2], top=got[3])
        x_pt, y_pt, w_pt, h_pt = box.as_pt()
        pdf.drawImage(
            ImageReader(art),
            x_pt + mm_to_pt(dx_mm),
            y_pt + mm_to_pt(dy_mm),
            width=w_pt,
            height=h_pt,
        )
        if tick:
            tick()
    _draw_crop_marks(pdf, layout, offset_mm)


def _draw_crop_marks(
    pdf: canvas.Canvas, layout: SheetLayout, offset_mm: Tuple[float, float] = (0.0, 0.0)
) -> None:
    dx_pt, dy_pt = mm_to_pt(offset_mm[0]), mm_to_pt(offset_mm[1])
    pdf.setLineWidth(MARK_WIDTH_PT)
    pdf.setStrokeColorRGB(0, 0, 0)
    for mark in layout.crop_marks():
        x1, y1, x2, y2 = mark.as_pt()
        pdf.line(x1 + dx_pt, y1 + dy_pt, x2 + dx_pt, y2 + dy_pt)


def export_batch(
    cards: Sequence[CardArt],
    out_path: Path,
    back: Optional[Image.Image] = None,
    layout: Optional[SheetLayout] = None,
    flip: Flip = Flip.LONG_EDGE,
    offset_mm: Tuple[float, float] = (0.0, 0.0),
    back_focus: Tuple[float, float] = (0.5, 0.5),
    progress: Optional[Callable[[int, int], None]] = None,
) -> ExportResult:
    """Lay ``cards`` out on sheets and write the PDF(s).

    ``offset_mm`` is this machine's measured duplex drift, applied to back
    pages only -- see ``tools/calibration_sheet.py``.  It belongs in gitignored
    ``printer.local.json``, never in the repo.

    ``progress`` is called as ``progress(done, total)`` after every image
    placed, so a caller can report real progress rather than an animation.  The
    unit is one drawn card, front or back -- the honest measure, since that is
    where the time goes on a deck of eighty.

    Raises ``GeometryError`` before writing anything if the layout would not
    register or if furniture would land on a card.
    """
    from ..spec.sheet import SHEET

    layout = layout or SHEET
    if not cards:
        raise ValueError("export_batch: nothing selected -- a batch needs a card")

    # Everything that can fail geometrically fails here, before any output.
    assert_registration(layout, flip)
    assert_art_inside_own_slot(layout)
    assert_clean_cards(layout, layout.crop_marks())

    pages = _chunk(list(cards), layout.cards_per_sheet)
    slots = list(layout.slots())

    total = len(cards) * (2 if back is not None else 1)
    state = {"done": 0}

    def tick() -> None:
        state["done"] += 1
        if progress:
            progress(state["done"], total)

    if progress:
        progress(0, total)
    page_size = (layout.paper.w_pt, layout.paper.h_pt)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    warnings: List[str] = []

    if flip is Flip.MANUAL:
        fronts = out_path.with_suffix(".fronts.pdf")
        backs = out_path.with_suffix(".backs.pdf")

        front_pdf = canvas.Canvas(str(fronts), pagesize=page_size)
        for page_cards in pages:
            warnings.extend(_draw_front_page(front_pdf, layout, page_cards, tick))
            front_pdf.showPage()
        front_pdf.save()

        written = [fronts]
        if back is not None:
            back_pdf = canvas.Canvas(str(backs), pagesize=page_size)
            for page_cards in pages:
                _draw_back_page(
                    back_pdf, layout, slots[: len(page_cards)], back, flip,
                    offset_mm, back_focus, tick,
                )
                back_pdf.showPage()
            back_pdf.save()
            written.append(backs)
    else:
        pdf = canvas.Canvas(str(out_path), pagesize=page_size)
        for page_cards in pages:
            warnings.extend(_draw_front_page(pdf, layout, page_cards, tick))
            pdf.showPage()
            if back is not None:
                _draw_back_page(
                    pdf, layout, slots[: len(page_cards)], back, flip, offset_mm,
                    back_focus, tick,
                )
                pdf.showPage()
        pdf.save()
        written = [out_path]

    return ExportResult(
        paths=written,
        sheets=len(pages),
        cards=len(cards),
        flip=flip,
        warnings=warnings,
    )
