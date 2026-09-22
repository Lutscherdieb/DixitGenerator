"""Crop-to-fill -- how an upload of any shape becomes a card-shaped image.

The card is the image, edge to edge: no letterbox band, no border, no fill.
So a source that is not 2:3 loses some of itself, and the only question is
*which* part.  ``focus`` answers that, and it is the per-card nudge the
overview exposes: a point in the source, in 0..1 coordinates, that the crop
window centres on as far as it can.

    focus = (0.5, 0.5)   centre  -- the default
    focus = (0.5, 0.0)   keep the top   (portrait subject, sky to lose)
    focus = (0.5, 1.0)   keep the bottom

Storing a focus point rather than a pixel rectangle means the crop survives
the source being re-uploaded at a different resolution, and means the same two
numbers work for the front art and for a back image.
"""

from __future__ import annotations

from typing import Tuple

from PIL import Image


def crop_to_fill(
    img: Image.Image,
    target_w: float,
    target_h: float,
    focus: Tuple[float, float] = (0.5, 0.5),
) -> Image.Image:
    """Return the largest ``target_w`` : ``target_h`` crop of ``img``.

    ``target_w``/``target_h`` are read as a ratio, so millimetres, points and
    pixels all work -- pass whichever the caller already has.

    ``focus`` is ``(x, y)`` in 0..1 of the source, y measured from the top.
    It is clamped, so a stored focus from a differently-shaped earlier upload
    degrades to "as close as this image allows" rather than raising.
    """
    if target_w <= 0 or target_h <= 0:
        raise ValueError(
            "target must be positive, got {}x{}".format(target_w, target_h)
        )

    target_aspect = target_w / target_h
    src_w, src_h = img.size
    src_aspect = src_w / src_h

    if src_aspect > target_aspect:
        # Source is wider than the card: keep full height, lose width.
        crop_w, crop_h = round(src_h * target_aspect), src_h
    else:
        # Source is taller than the card: keep full width, lose height.
        crop_w, crop_h = src_w, round(src_w / target_aspect)

    # Rounding can push the crop a pixel past the source on the kept axis.
    crop_w = min(crop_w, src_w)
    crop_h = min(crop_h, src_h)

    focus_x = min(max(focus[0], 0.0), 1.0)
    focus_y = min(max(focus[1], 0.0), 1.0)
    left = round((src_w - crop_w) * focus_x)
    top = round((src_h - crop_h) * focus_y)

    return img.crop((left, top, left + crop_w, top + crop_h))


def prepare_for_box(
    img: Image.Image,
    box_w_mm: float,
    box_h_mm: float,
    focus: Tuple[float, float] = (0.5, 0.5),
    rotate_deg: int = 0,
) -> Image.Image:
    """Crop ``img`` to the box's shape and rotate it, ready to be placed.

    Rotation happens **after** the crop, so ``focus`` always means the same
    thing in the source image regardless of how the back of a short-edge
    duplex sheet has to be turned.  The image is not resampled to a pixel
    size here: the PDF places it at a size in millimetres and the raster goes
    in at whatever resolution it has, which is what keeps a high-res source
    high-res.
    """
    out = crop_to_fill(img, box_w_mm, box_h_mm, focus)
    if rotate_deg % 360:
        out = out.rotate(rotate_deg, expand=True)
    return out
