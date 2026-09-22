"""``dixitgen.spec`` -- the single source of truth for every print measurement.

**Nothing outside this package may hardcode a measurement.**  Ask a
``CardFormat``, a ``SheetLayout``, or the conversions in ``units``.
``tools/check_geometry_literals.py`` enforces that by deriving its search list
from these objects, so a measurement added here is covered the day it exists.

Read the modules in this order:

    units    millimetres, points, pixels -- and where those ratios come from
    card     the printable card format (Dixit: 80 x 120 mm)
    sheet    the grid on the paper, the bleed, the crop marks, the duplex flip
    verify   the assertions that hold all of the above to the written PDF
"""

from .card import CARD_FORMATS, DIXIT, CardFormat
from .sheet import (
    A4,
    PAPER_SIZES,
    SHEET,
    Flip,
    PaperSize,
    Rect,
    Segment,
    SheetLayout,
)
from .units import (
    MM_PER_INCH,
    MM_TOLERANCE,
    PRINT_DPI,
    PT_PER_INCH,
    PT_TOLERANCE,
    effective_dpi,
    mm_to_pt,
    mm_to_px,
    pt_to_mm,
    px_to_mm,
)
from .verify import (
    GeometryError,
    art_warnings,
    assert_art_inside_own_slot,
    assert_clean_cards,
    assert_page_box,
    assert_placements_cover_cards,
    assert_registration,
)

__all__ = [
    # units
    "MM_PER_INCH",
    "PT_PER_INCH",
    "PRINT_DPI",
    "MM_TOLERANCE",
    "PT_TOLERANCE",
    "mm_to_pt",
    "pt_to_mm",
    "mm_to_px",
    "px_to_mm",
    "effective_dpi",
    # card
    "CardFormat",
    "DIXIT",
    "CARD_FORMATS",
    # sheet
    "PaperSize",
    "A4",
    "PAPER_SIZES",
    "SheetLayout",
    "SHEET",
    "Flip",
    "Rect",
    "Segment",
    # verify
    "GeometryError",
    "assert_registration",
    "assert_clean_cards",
    "assert_art_inside_own_slot",
    "assert_page_box",
    "assert_placements_cover_cards",
    "art_warnings",
]


def as_dict() -> dict:
    """The whole spec as plain JSON-able data.

    This is what the API serves at ``/api/meta`` and what the browser overview
    draws its numbers from, so the frontend never types a measurement of its
    own.  Keep it derived: every value here is read off a spec object.
    """
    sheet = SHEET
    return {
        "card": {
            "id": DIXIT.id,
            "label": DIXIT.label,
            "trim_w_mm": DIXIT.trim_w_mm,
            "trim_h_mm": DIXIT.trim_h_mm,
            "trim_w_px": DIXIT.trim_w_px,
            "trim_h_px": DIXIT.trim_h_px,
            "dpi": DIXIT.dpi,
            "aspect": DIXIT.aspect,
        },
        "paper": {
            "id": sheet.paper.id,
            "label": sheet.paper.label,
            "w_mm": sheet.paper.w_mm,
            "h_mm": sheet.paper.h_mm,
        },
        "sheet": {
            "cols": sheet.cols,
            "rows": sheet.rows,
            "cards_per_sheet": sheet.cards_per_sheet,
            "block_w_mm": sheet.block_w_mm,
            "block_h_mm": sheet.block_h_mm,
            "margin_x_mm": sheet.margin_x_mm,
            "margin_y_mm": sheet.margin_y_mm,
            "outer_bleed_mm": sheet.outer_bleed_mm,
        },
        "flips": [
            {"id": flip.value, "back_rotation_deg": SheetLayout.back_rotation_deg(flip)}
            for flip in Flip
        ],
    }
