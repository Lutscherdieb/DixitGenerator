"""Unit conversion -- the only place a millimetre becomes a point or a pixel.

Where the numbers come from
---------------------------
    1 in = 25.4 mm       the SI definition of the inch
    1 pt = 1 in / 72     the PostScript/PDF point
                         (MDN CSS length reference, retrieved 2026-09-22)
    300 DPI              what this project rasterises at

MDN also states ``1in = 96px``.  That is the **CSS reference pixel** and it is
not this project's pixel: nothing here renders through a browser.  Never carry
the 96 across into the print path -- see the blind spot recorded against the
``paper-and-pdf-units`` reference in REFERENCES.md.

**Nothing downstream may hardcode a measurement.  Ask this module, a
CardFormat, or a SheetLayout.**  ``tools/check_geometry_literals.py`` enforces
that by deriving its search list from these objects, so a measurement added
here is covered the day it exists.
"""

from __future__ import annotations

MM_PER_INCH = 25.4
PT_PER_INCH = 72.0
PRINT_DPI = 300

#: How close two millimetre figures must be to count as the same measurement.
#: One micrometre -- far below any printer's or blade's resolution, far above
#: the float noise of a mm -> pt -> mm round trip.
MM_TOLERANCE = 1e-3

#: The same idea in PDF user space.  A written page box is compared against
#: the derived one at this tolerance; anything looser would let a millimetre
#: of drift through, anything tighter would trip on reportlab's own rounding.
PT_TOLERANCE = 1e-2


def mm_to_pt(mm: float) -> float:
    """Millimetres to PDF user-space points (1/72 in)."""
    return mm / MM_PER_INCH * PT_PER_INCH


def pt_to_mm(pt: float) -> float:
    """PDF user-space points back to millimetres."""
    return pt / PT_PER_INCH * MM_PER_INCH


def mm_to_px(mm: float, dpi: int = PRINT_DPI) -> int:
    """Millimetres to whole raster pixels at ``dpi``.

    Rounds, because a fractional pixel is not a thing a raster can hold; the
    caller that cares about the lost fraction should work in millimetres and
    convert once, at the edge.
    """
    return round(mm / MM_PER_INCH * dpi)


def px_to_mm(px: float, dpi: int = PRINT_DPI) -> float:
    """Raster pixels at ``dpi`` back to millimetres."""
    return px / dpi * MM_PER_INCH


def effective_dpi(pixels: int, placed_mm: float) -> float:
    """The real resolution of ``pixels`` of source art placed across ``placed_mm``.

    This is the number that decides whether an upload prints sharply: a
    4000 px image placed across 80 mm resolves at 1270 DPI, a 400 px one at
    127 DPI and will look soft no matter how good the source was.
    """
    if placed_mm <= 0:
        raise ValueError("placed_mm must be positive, got {!r}".format(placed_mm))
    return pixels / (placed_mm / MM_PER_INCH)
