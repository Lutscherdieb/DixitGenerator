"""The printable card format -- one object, every card measurement derived from it.

Where the numbers come from
---------------------------
The physical Dixit card.  Libellud publishes no dimension; the available
figures are sleeve manufacturers' and retailers' (see the ``dixit-card-spec``
entry in REFERENCES.md).  They disagree by a millimetre on the width:

    MayDay / Sleeve Kings / Gamegenic   sleeve 80 x 120 mm  ("Dixit"/"Magnum")
    one retailer's card listing         card   79 x 120 mm

We print **80 x 120 mm**, the sleeve standard, because a hand-cut and
laminated card grows rather than shrinks, and because 80 x 120 is the size a
sleeve is built to accept.  Do not "fix" this to 79 -- that disagreement is a
recorded blind spot, not an oversight.
"""

from __future__ import annotations

from dataclasses import dataclass

from .units import PRINT_DPI, mm_to_pt, mm_to_px


@dataclass(frozen=True)
class CardFormat:
    """One printable card format.  Every measurement below is derived, never stored."""

    id: str
    label: str
    trim_w_mm: float
    trim_h_mm: float
    dpi: int = PRINT_DPI

    def __post_init__(self) -> None:
        for axis, mm in (("width", self.trim_w_mm), ("height", self.trim_h_mm)):
            if mm <= 0:
                raise ValueError(
                    "card format {!r}: trim {} must be positive, got {!r}".format(
                        self.id, axis, mm
                    )
                )

    # -- points: what a PDF is drawn in ------------------------------------
    @property
    def trim_w_pt(self) -> float:
        return mm_to_pt(self.trim_w_mm)

    @property
    def trim_h_pt(self) -> float:
        return mm_to_pt(self.trim_h_mm)

    # -- pixels: what artwork must supply to print sharply -----------------
    @property
    def trim_w_px(self) -> int:
        return mm_to_px(self.trim_w_mm, self.dpi)

    @property
    def trim_h_px(self) -> int:
        return mm_to_px(self.trim_h_mm, self.dpi)

    @property
    def aspect(self) -> float:
        """Width divided by height.  Dixit is 2:3 exactly."""
        return self.trim_w_mm / self.trim_h_mm

    def art_is_soft(self, px_w: int, px_h: int, placed_w_mm: float = 0.0,
                    placed_h_mm: float = 0.0) -> bool:
        """Would art of ``px_w`` x ``px_h`` print soft across this card?

        Advisory only -- a warning, never a block.  A deliberately low-res or
        painterly source is the author's call, and PROJECT.md says so.

        ``placed_*_mm`` default to the card trim; pass the bled box instead
        when the art is stretched past the trim line, because that is the
        width it is actually resolving across.
        """
        w_mm = placed_w_mm or self.trim_w_mm
        h_mm = placed_h_mm or self.trim_h_mm
        # Compare pixel counts, not computed DPI.  Art of exactly the derived
        # size (945 x 1417 for a Dixit card) resolves at 299.93 DPI on the
        # long axis because 1417 is the *rounded* pixel count -- a float
        # comparison against 300 calls the exactly-right image soft.
        return px_w < mm_to_px(w_mm, self.dpi) or px_h < mm_to_px(h_mm, self.dpi)


#: The format this project prints.  Others exist only as cross-checks in the
#: verify gate -- see PROJECT.md: a conversion checked only against the
#: numbers it was built for is unfalsifiable.
DIXIT = CardFormat(
    id="dixit",
    label="Dixit (80 x 120 mm)",
    trim_w_mm=80.0,
    trim_h_mm=120.0,
)

CARD_FORMATS = {DIXIT.id: DIXIT}
