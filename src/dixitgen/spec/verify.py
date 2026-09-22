"""Geometry assertions -- the enforcement behind PROJECT.md's quality bars.

These are called from **two** places, and that is the point:

* inside the export, before a PDF is written, so a misregistered batch never
  reaches the output directory;
* from ``tests/run_tests.py``, against a PDF that has been **parsed back off
  disk**, so the gate checks the artefact rather than the intention.

Assertions raise ``GeometryError``.  None of them warns.  PROJECT.md: *a
misregistered back is a failed export, not a warning* -- if one of these ever
becomes inconvenient, the layout is wrong, not the assertion.

The one advisory in this module is ``art_warnings``, which returns strings
instead of raising: artwork resolution is the author's call.
"""

from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

from .card import CardFormat
from .sheet import Flip, PaperSize, Rect, Segment, SheetLayout
from .units import MM_TOLERANCE, PT_TOLERANCE, effective_dpi, pt_to_mm


class GeometryError(AssertionError):
    """A sheet or a written PDF does not match the spec it was built from."""


def assert_registration(layout: SheetLayout, flip: Flip) -> None:
    """Every back slot must land exactly behind its front slot.

    Two independent things are checked, because either alone is satisfiable by
    a wrong mapping:

    1. **The mapping is an involution.**  Turning a sheet over twice returns
       it, so ``back_slot(back_slot(s)) == s``.  A mapping that fails this
       does not describe a physical flip at all.
    2. **The geometry actually mirrors.**  The back slot's box must be the
       front box reflected in the page's centre line for that flip.  This is
       what catches a correct-looking permutation applied to an off-centre
       block, where the slots pair up but the paper does not.
    """
    paper = layout.paper
    for row, col in layout.slots():
        back = layout.back_slot(row, col, flip)
        there_and_back = layout.back_slot(back[0], back[1], flip)
        if there_and_back != (row, col):
            raise GeometryError(
                "{}: back_slot is not an involution -- front ({}, {}) maps to "
                "{} which maps to {}, not back to the front slot".format(
                    flip.value, row, col, back, there_and_back
                )
            )

        front_box = layout.card_box(row, col)
        back_box = layout.card_box(*back)
        if flip is Flip.SHORT_EDGE:
            axis = "horizontal centre line"
            want_x = front_box.x_mm
            want_y = paper.h_mm - front_box.top_mm
        else:
            axis = "vertical centre line"
            want_x = paper.w_mm - front_box.right_mm
            want_y = front_box.y_mm

        if (
            abs(back_box.x_mm - want_x) > MM_TOLERANCE
            or abs(back_box.y_mm - want_y) > MM_TOLERANCE
        ):
            raise GeometryError(
                "{}: front slot ({}, {}) at ({:.4f}, {:.4f})mm mirrors in the {} "
                "to ({:.4f}, {:.4f})mm, but back slot {} sits at "
                "({:.4f}, {:.4f})mm -- the block is not centred on the "
                "paper".format(
                    flip.value,
                    row,
                    col,
                    front_box.x_mm,
                    front_box.y_mm,
                    axis,
                    want_x,
                    want_y,
                    back,
                    back_box.x_mm,
                    back_box.y_mm,
                )
            )


def assert_clean_cards(layout: SheetLayout, drawn: Iterable[Segment]) -> None:
    """No drawn element may intersect a card box.

    PROJECT.md's defining constraint: the card *is* the image.  Crop marks,
    page furniture and debug overlays live in the paper margin.  A 0.2 mm
    intrusion is invisible on screen and obvious on a laminated card, which is
    exactly why this is an assertion and not a review by eye.
    """
    boxes = [(slot, layout.card_box(*slot)) for slot in layout.slots()]
    for element in drawn:
        bbox = element.bbox
        for slot, box in boxes:
            if bbox.overlaps(box):
                raise GeometryError(
                    "drawn element {} enters card box {} at "
                    "({:.4f}, {:.4f}) {:.4f}x{:.4f}mm -- furniture belongs in "
                    "the paper margin".format(
                        element, slot, box.x_mm, box.y_mm, box.w_mm, box.h_mm
                    )
                )


def assert_art_inside_own_slot(layout: SheetLayout) -> None:
    """A slot's art may bleed off the paper edge, never onto its neighbour.

    ``art_box`` grows only on sides that sit on the block's outer edge, so this
    holds by construction -- and is asserted anyway, because "holds by
    construction" is what every broken invariant was before it broke.
    """
    for row, col in layout.slots():
        art = layout.art_box(row, col)
        for other_row, other_col in layout.slots():
            if (other_row, other_col) == (row, col):
                continue
            neighbour = layout.card_box(other_row, other_col)
            if art.overlaps(neighbour):
                raise GeometryError(
                    "art for slot ({}, {}) overlaps the card box of slot "
                    "({}, {}) -- bleed may only grow outward from the "
                    "block".format(row, col, other_row, other_col)
                )


def assert_page_box(width_pt: float, height_pt: float, paper: PaperSize) -> None:
    """A written page box must be the paper, to within a hundredth of a point."""
    if (
        abs(width_pt - paper.w_pt) > PT_TOLERANCE
        or abs(height_pt - paper.h_pt) > PT_TOLERANCE
    ):
        raise GeometryError(
            "page box is {:.4f} x {:.4f}pt, expected {} at {:.4f} x {:.4f}pt "
            "({:.4f} x {:.4f}mm vs {} x {}mm)".format(
                width_pt,
                height_pt,
                paper.label,
                paper.w_pt,
                paper.h_pt,
                pt_to_mm(width_pt),
                pt_to_mm(height_pt),
                paper.w_mm,
                paper.h_mm,
            )
        )


def assert_placements_cover_cards(
    placements: Sequence[Tuple[float, float, float, float]],
    layout: SheetLayout,
    slots: Sequence[Tuple[int, int]],
    what: str = "art",
) -> None:
    """Art placements parsed out of a PDF must frame their cards correctly.

    The invariant is not equality with ``art_box``.  ``art_box`` is a *maximum*:
    how much bleed a slot actually gets depends on how many spare pixels the
    source had outside its trim crop, so a legitimate placement is anywhere
    between the card box and the nominal art box.  What must always hold:

    1. every named slot has exactly one placement;
    2. that placement **contains the slot's whole card box** -- otherwise the
       cut would leave bare paper inside the card;
    3. it does not exceed the nominal art box -- otherwise art would spill onto
       a neighbour or past the bleed allowance.

    ``placements`` are ``(x, y, w, h)`` in **millimetres**, in any order: a PDF
    content stream has no obligation to draw in reading order.
    """
    if len(placements) != len(slots):
        raise GeometryError(
            "found {} {} placements on the page, expected {} (slots {})".format(
                len(placements), what, len(slots), list(slots)
            )
        )

    unmatched = list(placements)
    for slot in slots:
        card = layout.card_box(*slot)
        limit = layout.art_box(*slot)
        for i, (x, y, w, h) in enumerate(unmatched):
            placed = Rect(x, y, w, h)
            contains_card = (
                placed.x_mm <= card.x_mm + MM_TOLERANCE
                and placed.y_mm <= card.y_mm + MM_TOLERANCE
                and placed.right_mm >= card.right_mm - MM_TOLERANCE
                and placed.top_mm >= card.top_mm - MM_TOLERANCE
            )
            within_limit = (
                placed.x_mm >= limit.x_mm - MM_TOLERANCE
                and placed.y_mm >= limit.y_mm - MM_TOLERANCE
                and placed.right_mm <= limit.right_mm + MM_TOLERANCE
                and placed.top_mm <= limit.top_mm + MM_TOLERANCE
            )
            if contains_card and within_limit:
                unmatched.pop(i)
                break
        else:
            raise GeometryError(
                "no {} placement frames slot {}: it must contain the card box "
                "({:.3f}, {:.3f}) {:.3f}x{:.3f}mm and stay inside "
                "({:.3f}, {:.3f}) {:.3f}x{:.3f}mm; the page has {}".format(
                    what,
                    slot,
                    card.x_mm,
                    card.y_mm,
                    card.w_mm,
                    card.h_mm,
                    limit.x_mm,
                    limit.y_mm,
                    limit.w_mm,
                    limit.h_mm,
                    ["({:.2f}, {:.2f}) {:.2f}x{:.2f}".format(*p) for p in placements],
                )
            )


def art_warnings(
    card: CardFormat, sources: Iterable[Tuple[str, int, int]], placed: Rect
) -> List[str]:
    """Advisory soft-print warnings -- returns strings, never raises.

    PROJECT.md: artwork resolution is validated *advisorily*.  A deliberately
    low-res or painterly source is the author's call, so this reports and the
    caller decides.
    """
    notes: List[str] = []
    for name, px_w, px_h in sources:
        if card.art_is_soft(px_w, px_h, placed.w_mm, placed.h_mm):
            notes.append(
                "{}: {}x{}px across {:.1f}x{:.1f}mm resolves at {:.0f}x{:.0f} DPI, "
                "below the {} DPI this prints at -- it will look soft".format(
                    name,
                    px_w,
                    px_h,
                    placed.w_mm,
                    placed.h_mm,
                    effective_dpi(px_w, placed.w_mm),
                    effective_dpi(px_h, placed.h_mm),
                    card.dpi,
                )
            )
    return notes
