"""Grid thumbnails.

A thumbnail here is **cropped to the card's shape**, not to the source's. The
point of the overview is to show what will print, so a tile must show the same
crop the PDF will place -- otherwise you pick a card that looks right in the
grid and discover the crop at the guillotine.

That makes the thumbnail a function of the focus point, so it is regenerated
whenever the focus changes. `repo.set_focus` is the one place that happens.
"""

from __future__ import annotations

import io
from typing import Tuple

from PIL import Image

from ..spec import DIXIT
from .crop import crop_to_fill

#: Longest edge of a grid tile, in screen pixels. Not a print measurement --
#: it never reaches a PDF -- so it is not owned by `dixitgen.spec`.
THUMB_MAX_PX = 400

#: JPEG, because a tile is opaque card art and a 400px JPEG is a few KB while
#: the PNG of the same tile is ten times that, multiplied by every card in the
#: library on every page load.
THUMB_QUALITY = 85


def make_thumb(
    img: Image.Image,
    focus: Tuple[float, float] = (0.5, 0.5),
    max_px: int = THUMB_MAX_PX,
) -> bytes:
    """A small JPEG of ``img`` cropped to the card's aspect at ``focus``."""
    cropped = crop_to_fill(img, DIXIT.trim_w_mm, DIXIT.trim_h_mm, focus)
    cropped.thumbnail((max_px, max_px), Image.LANCZOS)
    if cropped.mode not in ("RGB", "L"):
        cropped = cropped.convert("RGB")
    buffer = io.BytesIO()
    cropped.save(buffer, format="JPEG", quality=THUMB_QUALITY, optimize=True)
    return buffer.getvalue()
