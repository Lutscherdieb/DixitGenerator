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

The trim is the card; bleed is extra
------------------------------------
``crop_with_bleed`` defines a card as the **trim** crop -- exactly what
``crop_to_fill`` returns, and exactly what the grid thumbnail shows -- and then
takes bleed from source pixels *outside* it, per side, clamped to what the
source actually has.

That ordering is the whole point.  Scaling the art to fill the *bled* box
instead makes the trim line cut into the picture, so the printed card is a
tighter crop than the preview; and because bleed only exists on the block's
outer edges, which part you lose then depends on which slot the card landed
in.  Same card, different position, different framing.  Fixed 2026-09-23 after
the author measured it on a real export.

One consequence is structural and worth knowing: ``crop_to_fill`` always uses
**100% of one axis**, so that axis never has a spare pixel to bleed with.
Partial bleed is therefore the normal outcome, not a sign of undersized art.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from PIL import Image

#: Bleed is named in PDF terms -- (left, bottom, right, top) -- because that is
#: how the sheet layout names it and how reportlab draws.
Sides = Tuple[float, float, float, float]

NO_BLEED: Sides = (0.0, 0.0, 0.0, 0.0)


@dataclass(frozen=True)
class BleedCrop:
    """A cropped image and the bleed it actually managed to include."""

    image: Image.Image
    left_mm: float
    bottom_mm: float
    right_mm: float
    top_mm: float

    @property
    def sides(self) -> Sides:
        return (self.left_mm, self.bottom_mm, self.right_mm, self.top_mm)

    @property
    def is_short(self) -> bool:
        """True when any requested side could not be filled -- caller may warn."""
        return getattr(self, "_short", False)


def fill_rect(
    src_w: int,
    src_h: int,
    target_w: float,
    target_h: float,
    focus: Tuple[float, float] = (0.5, 0.5),
) -> Tuple[int, int, int, int]:
    """The largest ``target_w``:``target_h`` rectangle inside ``src_w`` x ``src_h``.

    Returns ``(left, top, width, height)`` in source pixels.  Note that one of
    width/height always equals the source's own -- the crop is maximal, so one
    axis is fully consumed.
    """
    if target_w <= 0 or target_h <= 0:
        raise ValueError("target must be positive, got {}x{}".format(target_w, target_h))

    target_aspect = target_w / target_h
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
    return (left, top, crop_w, crop_h)


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

    This is what the grid thumbnail shows and what a cut card shows: the two
    are the same crop by construction.
    """
    left, top, crop_w, crop_h = fill_rect(*img.size, target_w, target_h, focus)
    return img.crop((left, top, left + crop_w, top + crop_h))


def crop_with_bleed(
    img: Image.Image,
    trim_w_mm: float,
    trim_h_mm: float,
    focus: Tuple[float, float] = (0.5, 0.5),
    bleed: Sides = NO_BLEED,
) -> BleedCrop:
    """The trim crop, extended outward by whatever bleed the source can supply.

    The returned image maps onto the trim box **grown by the returned sides**.
    Because the achieved sides are reported rather than assumed, the drawn box
    always equals the drawn image -- so a side that could not bleed produces a
    smaller box, never a white band.
    """
    left, top, crop_w, crop_h = fill_rect(*img.size, trim_w_mm, trim_h_mm, focus)
    src_w, src_h = img.size

    px_per_mm_x = crop_w / trim_w_mm
    px_per_mm_y = crop_h / trim_h_mm

    want_left, want_bottom, want_right, want_top = bleed
    # Image rows run top-down; the sheet's "top" is the image's top because the
    # art is placed upright.
    take_left = min(int(want_left * px_per_mm_x), left)
    take_top = min(int(want_top * px_per_mm_y), top)
    take_right = min(int(want_right * px_per_mm_x), src_w - (left + crop_w))
    take_bottom = min(int(want_bottom * px_per_mm_y), src_h - (top + crop_h))

    take_left = max(take_left, 0)
    take_top = max(take_top, 0)
    take_right = max(take_right, 0)
    take_bottom = max(take_bottom, 0)

    out = img.crop(
        (
            left - take_left,
            top - take_top,
            left + crop_w + take_right,
            top + crop_h + take_bottom,
        )
    )
    result = BleedCrop(
        image=out,
        left_mm=take_left / px_per_mm_x,
        bottom_mm=take_bottom / px_per_mm_y,
        right_mm=take_right / px_per_mm_x,
        top_mm=take_top / px_per_mm_y,
    )
    object.__setattr__(
        result,
        "_short",
        any(
            achieved + 1e-6 < wanted
            for achieved, wanted in zip(result.sides, bleed)
        ),
    )
    return result


def _reflect_pad(
    img: Image.Image, left: int, top: int, right: int, bottom: int
) -> Image.Image:
    """``img`` grown by mirroring its own edges outward.

    Mirroring rather than a solid fill: a press cuts somewhere inside the bleed
    and whatever is there shows on the card edge, so it has to continue the
    picture.  A white or black band would print as a sliver of exactly the
    thing bleed exists to prevent.

    If a side is asked for more than the image is wide or tall -- only possible
    for a source far below print resolution -- the mirror is topped up by
    replicating the outermost row or column, which is ugly but bounded.
    """
    if not any((left, top, right, bottom)):
        return img

    w, h = img.size
    out = Image.new(img.mode, (w + left + right, h + top + bottom))
    out.paste(img, (left, top))

    if left:
        n = min(left, w)
        out.paste(img.crop((0, 0, n, h)).transpose(Image.FLIP_LEFT_RIGHT), (left - n, top))
        if n < left:
            out.paste(img.crop((0, 0, 1, h)).resize((left - n, h)), (0, top))
    if right:
        n = min(right, w)
        out.paste(
            img.crop((w - n, 0, w, h)).transpose(Image.FLIP_LEFT_RIGHT), (left + w, top)
        )
        if n < right:
            out.paste(
                img.crop((w - 1, 0, w, h)).resize((right - n, h)), (left + w + n, top)
            )

    # Take the full-width band back off the canvas so the corners come along
    # with the vertical mirror instead of needing four more cases.
    band = out.crop((0, top, out.width, top + h))
    bw, bh = band.size
    if top:
        n = min(top, bh)
        out.paste(band.crop((0, 0, bw, n)).transpose(Image.FLIP_TOP_BOTTOM), (0, top - n))
        if n < top:
            out.paste(band.crop((0, 0, bw, 1)).resize((bw, top - n)), (0, 0))
    if bottom:
        n = min(bottom, bh)
        out.paste(
            band.crop((0, bh - n, bw, bh)).transpose(Image.FLIP_TOP_BOTTOM), (0, top + h)
        )
        if n < bottom:
            out.paste(
                band.crop((0, bh - 1, bw, bh)).resize((bw, bottom - n)),
                (0, top + h + n),
            )
    return out


def crop_with_full_bleed(
    img: Image.Image,
    trim_w_mm: float,
    trim_h_mm: float,
    bleed_mm: float,
    focus: Tuple[float, float] = (0.5, 0.5),
) -> BleedCrop:
    """The trim crop with ``bleed_mm`` on **every** side, guaranteed.

    This is the press path, and it differs from ``crop_with_bleed`` in the one
    way that matters: the requested bleed is always delivered.  Source pixels
    outside the trim are used where they exist, and the shortfall is mirrored
    (see ``_reflect_pad``).

    The trim region of the result is byte-identical to ``crop_to_fill`` on the
    same arguments, which is the whole point -- the sheet PDF, the plain image
    export and the press files all show one framing.  Cropping to the bled
    rectangle instead would be shorter and would frame each output differently;
    see ``dixitgen.spec.press``.

    Nothing is resampled: the bleed is measured in source pixels at whatever
    resolution the crop already has, so the returned image is the trim crop's
    own resolution plus its bleed.
    """
    if bleed_mm < 0:
        raise ValueError("bleed_mm must not be negative, got {!r}".format(bleed_mm))

    left, top, crop_w, crop_h = fill_rect(*img.size, trim_w_mm, trim_h_mm, focus)
    src_w, src_h = img.size

    px_per_mm_x = crop_w / trim_w_mm
    px_per_mm_y = crop_h / trim_h_mm
    want_x = round(bleed_mm * px_per_mm_x)
    want_y = round(bleed_mm * px_per_mm_y)

    # Real pixels first, as far as the source reaches on each side.
    take_left = max(min(want_x, left), 0)
    take_top = max(min(want_y, top), 0)
    take_right = max(min(want_x, src_w - (left + crop_w)), 0)
    take_bottom = max(min(want_y, src_h - (top + crop_h)), 0)

    real = img.crop(
        (
            left - take_left,
            top - take_top,
            left + crop_w + take_right,
            top + crop_h + take_bottom,
        )
    )
    out = _reflect_pad(
        real,
        left=want_x - take_left,
        top=want_y - take_top,
        right=want_x - take_right,
        bottom=want_y - take_bottom,
    )

    # Reported in millimetres off the same ratio the pixels were taken at, so
    # the caller can place the image without recomputing anything.
    return BleedCrop(
        image=out,
        left_mm=want_x / px_per_mm_x,
        bottom_mm=want_y / px_per_mm_y,
        right_mm=want_x / px_per_mm_x,
        top_mm=want_y / px_per_mm_y,
    )


def rotate_sides(sides: Sides) -> Sides:
    """The same sides seen after a 180-degree turn: left<->right, bottom<->top.

    Used for a short-edge duplex back: the bleed has to be requested on the
    *opposite* sides before the rotation so that it lands correctly after it.
    """
    left, bottom, right, top = sides
    return (right, top, left, bottom)


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

    For card art the export uses ``crop_with_bleed`` instead -- this remains
    for the case where the target box *is* the intended framing.
    """
    out = crop_to_fill(img, box_w_mm, box_h_mm, focus)
    if rotate_deg % 360:
        out = out.rotate(rotate_deg, expand=True)
    return out
