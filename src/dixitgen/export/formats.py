"""The output formats an export can produce, described once.

There are three, and the difference that matters is **sheets versus images**:

    a4-pdf     the primary output -- A4 duplex sheets, 2x2, crop marks in the
               margin.  Duplex mode and the printer calibration offset apply.
    mpc-dixit  one image file per card: the trim crop plus a press's bleed
               outside it.  No sheets, so no duplex and no calibration.
    crops      one image file per card, the trim crop alone, at the source's
               own resolution.  No sheets either.

All three crop to the same trim rectangle, so a card is framed identically
whichever one is chosen -- see ``card_images``.

Every label and every number below is **derived from the spec objects**, so the
browser dialog can render the menu straight from ``/api/meta`` without typing a
measurement of its own -- the rule in ``dixitgen.spec``'s docstring.  Add a
format here and it appears in the dialog with no frontend edit.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from ..spec.card import DIXIT, CardFormat
from ..spec.press import MPC_DIXIT, PressFormat
from ..spec.sheet import SHEET


class OutputFormat(str, Enum):
    """What an export writes.  The value travels in the API payload."""

    #: A4 duplex sheets -- what this project is for.
    A4_PDF = "a4-pdf"

    #: Per-card images at this project's card size, with a press's bleed.
    MPC = "mpc-dixit"

    #: Per-card images, the trim crop, no bleed, no resampling.
    CROPS = "crops"


@dataclass(frozen=True)
class OutputOption:
    """One entry in the export dialog's format menu."""

    id: str
    label: str
    detail: str
    #: ``"sheets"`` or ``"images"`` -- the frontend shows the duplex and
    #: calibration controls only for the former, because a per-card image has
    #: no front/back registration to get wrong.
    kind: str
    card: CardFormat
    press: Optional[PressFormat] = None

    @property
    def uses_duplex(self) -> bool:
        return self.kind == "sheets"

    @property
    def suffix(self) -> str:
        return ".pdf" if self.kind == "sheets" else ".zip"

    def as_dict(self) -> dict:
        out = {
            "id": self.id,
            "label": self.label,
            "detail": self.detail,
            "kind": self.kind,
            "uses_duplex": self.uses_duplex,
            "suffix": self.suffix,
            "card": {
                "id": self.card.id,
                "label": self.card.label,
                "trim_w_mm": self.card.trim_w_mm,
                "trim_h_mm": self.card.trim_h_mm,
                "trim_w_px": self.card.trim_w_px,
                "trim_h_px": self.card.trim_h_px,
            },
        }
        if self.press is not None:
            out["press"] = {
                "id": self.press.id,
                "service": self.press.service,
                "bleed_px": self.press.bleed_px,
                "upload_w_px": self.press.upload_w_px,
                "upload_h_px": self.press.upload_h_px,
            }
        return out


def _options() -> List[OutputOption]:
    return [
        OutputOption(
            id=OutputFormat.A4_PDF.value,
            label="A4 duplex sheets (PDF)",
            detail=(
                "{} per card, {}x{} to a {} sheet, crop marks in the "
                "margin.".format(
                    DIXIT.label, SHEET.cols, SHEET.rows, SHEET.paper.label
                )
            ),
            kind="sheets",
            card=DIXIT,
        ),
        OutputOption(
            id=OutputFormat.MPC.value,
            label="MakePlayingCards ready (images)",
            detail=(
                "One {}x{} px image per card -- the same {:.0f} x {:.0f} mm crop "
                "as the sheets, plus {} px of bleed a side. Not an MPC stock "
                "size; needs their custom-size path.".format(
                    MPC_DIXIT.upload_w_px,
                    MPC_DIXIT.upload_h_px,
                    MPC_DIXIT.card.trim_w_mm,
                    MPC_DIXIT.card.trim_h_mm,
                    MPC_DIXIT.bleed_px,
                )
            ),
            kind="images",
            card=MPC_DIXIT.card,
            press=MPC_DIXIT,
        ),
        OutputOption(
            id=OutputFormat.CROPS.value,
            label="Cropped images only",
            detail=(
                "The {:.0f} x {:.0f} mm trim crop each tile shows, at the "
                "source's own resolution -- nothing is resampled.".format(
                    DIXIT.trim_w_mm, DIXIT.trim_h_mm
                )
            ),
            kind="images",
            card=DIXIT,
        ),
    ]


#: Keyed by id, in menu order.
OUTPUTS = {option.id: option for option in _options()}


def option_for(value: str) -> OutputOption:
    """The option for an API payload's ``format``, or ``KeyError``."""
    return OUTPUTS[OutputFormat(value).value]


def as_dicts() -> List[dict]:
    """The menu, for ``/api/meta``."""
    return [option.as_dict() for option in OUTPUTS.values()]
