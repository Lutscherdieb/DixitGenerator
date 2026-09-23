"""Press profiles -- a card format plus the bleed a print service demands.

Why this exists at all
----------------------
PROJECT.md's original non-goal said this project would never speak to a print
service, because the output targets a home printer, a guillotine and a
laminator.  That was reversed on 2026-09-23 (see the reversal note in
PROJECT.md); the reversal is narrow, and this module is the whole of it:

    * one service, MakePlayingCards, one product size -- this project's own;
    * no ordering, no upload, no account -- it writes image files and stops;
    * the A4 path is untouched and remains the primary output.

The sibling project ``CardGenerator``'s ``Profile`` model is still not imported
-- its numbers are its own service's, and a press number copied between
projects is exactly the second source of truth this repo exists to avoid.

Bleed here is the opposite of the sheet's bleed
-----------------------------------------------
``SheetLayout.outer_bleed_mm`` grows art *outward* from the trim, takes only
what a source happens to have spare, and currently sits at zero -- on a sheet
you cut yourself, an asymmetric bleed is worse than none (PROJECT.md).

A press cuts on its own line with a mechanical tolerance, so bleed there is
**mandatory and symmetric**: every uploaded file must carry it on all four
sides, and a side that is short prints a white sliver.

The trim crop stays the framing regardless.  The bleed is added *outside* the
trim crop -- from real source pixels where the source has spare ones, mirrored
where it does not -- so the card a press cuts shows exactly what the A4 sheet
and the exported image show.  Cropping to the bled rectangle instead would have
been simpler and was rejected on 2026-09-23: it makes the trim line eat into
the picture, so the same card is framed differently in each output.

Where the numbers come from
---------------------------
MakePlayingCards publishes, for the tarot card (``mpc-card-spec`` in
REFERENCES.md, retrieved 2026-09-23):

    printed size          2.75 x 4.75 in
    bleed                 1/8 in, "approx 36 pixels based on a 300dpi image"
    safe area             a further 1/8 in inside the trim
    minimum upload        897 x 1497 px at 300 DPI

**36 px is the figure written down, not the 1/8 in**, because MPC's own
template is built from the pixel count: 1/8 in at 300 DPI is 37.5 px, and the
897 x 1497 they publish only reconciles with 36.  ``tests/run_tests.py``
asserts that this module reproduces 897 x 1497 -- a derivation checked only
against the numbers it was built from cannot fail.

The safe area is deliberately **not** modelled.  It exists to keep text and
logos away from the cut, and nothing but the card's own image ever prints here
(PROJECT.md's defining constraint), so there is nothing for it to protect.
"""

from __future__ import annotations

from dataclasses import dataclass

from .card import DIXIT, TAROT_MPC, CardFormat
from .units import px_to_mm


@dataclass(frozen=True)
class PressFormat:
    """A card format plus one service's published bleed.

    ``bleed_px`` is per side, at ``card.dpi``, and is the only figure stored:
    everything else on this class is derived from it and from ``card``.
    """

    id: str
    label: str
    service: str
    card: CardFormat
    bleed_px: int

    def __post_init__(self) -> None:
        if self.bleed_px < 0:
            raise ValueError(
                "press format {!r}: bleed_px must not be negative, got {!r}".format(
                    self.id, self.bleed_px
                )
            )

    # -- the uploaded rectangle --------------------------------------------
    @property
    def upload_w_px(self) -> int:
        """Full artwork width the service expects: trim plus bleed both sides."""
        return self.card.trim_w_px + 2 * self.bleed_px

    @property
    def upload_h_px(self) -> int:
        return self.card.trim_h_px + 2 * self.bleed_px

    @property
    def bleed_mm(self) -> float:
        return px_to_mm(self.bleed_px, self.card.dpi)

    @property
    def bled_w_mm(self) -> float:
        return self.card.trim_w_mm + 2 * self.bleed_mm

    @property
    def bled_h_mm(self) -> float:
        return self.card.trim_h_mm + 2 * self.bleed_mm

    @property
    def aspect(self) -> float:
        """Width over height of the bled rectangle.

        Reported for completeness, **not** used as a crop shape: the source is
        cropped to ``card``'s trim aspect and the bleed is added outside it, so
        that every output frames a card identically.  Adding equal bleed to a
        non-square changes the ratio, which is exactly why cropping to this
        number would deviate from the sheet output.
        """
        return self.bled_w_mm / self.bled_h_mm

    def art_is_soft(self, px_w: int, px_h: int) -> bool:
        """Is art of this pixel size below the service's published minimum?

        Advisory, like ``CardFormat.art_is_soft``: PROJECT.md makes resolution
        a warning and never a block.  Compared against the derived integer
        upload size rather than a recomputed DPI, for the reason recorded in
        ``CardFormat.art_is_soft``.
        """
        return px_w < self.upload_w_px or px_h < self.upload_h_px


#: MakePlayingCards' **stock** tarot product, exactly as they publish it.
#:
#: This project does not print it.  It is here as the cross-check: the
#: derivation below must reproduce MPC's published 897 x 1497 px upload size,
#: and ``tests/run_tests.py`` asserts that.  A bleed model checked only against
#: the size it was built for cannot fail -- the same reason the verify gate
#: measures an MTG card it will never lay out.
#:
#: It is also the documented fallback: if MPC decline the custom size below,
#: pointing ``SheetLayout.fit`` at ``TAROT_MPC`` moves the whole project --
#: sheets, crops and press files alike -- onto this product in one edit.
MPC_TAROT_STOCK = PressFormat(
    id="mpc-tarot-stock",
    label="MakePlayingCards tarot (stock)",
    service="MakePlayingCards",
    card=TAROT_MPC,
    bleed_px=36,
)

#: What the MPC export actually writes: **this project's own card size** with
#: MPC's bleed around it.
#:
#: Chosen on 2026-09-23 over the stock tarot product so that one crop serves
#: every output.  A tarot card is 10.15 mm narrower than a Dixit card, so
#: cropping to it would have made the pressed card show a different slice of
#: the art than the A4 sheet and the exported image -- three outputs, three
#: framings.  The trim crop is now the single source of framing and the bleed
#: is added outside it.
#:
#: The cost is that 80 x 120 mm is not an MPC stock size: ordering goes through
#: their custom-requirements path, and they may decline it.  If they do, see
#: ``MPC_TAROT_STOCK`` above.
MPC_DIXIT = PressFormat(
    id="mpc-dixit",
    label="MakePlayingCards, Dixit size (custom)",
    service="MakePlayingCards",
    card=DIXIT,
    bleed_px=36,
)

PRESS_FORMATS = {fmt.id: fmt for fmt in (MPC_DIXIT, MPC_TAROT_STOCK)}
