"""Read a written PDF back into plain geometry, in millimetres.

Why this exists
---------------
PROJECT.md's verify method says the gate parses the produced PDF back.  That
wording is deliberate: asserting the export against the ``SheetLayout`` it was
handed only proves the code agrees with itself.  Everything in this module
reads the **file**, so a drawing bug between the layout and the page is
visible.

What it understands
-------------------
Enough of a PDF content stream to place things: the graphics state stack
(``q``/``Q``), the current transformation matrix (``cm``), image draws
(``Do`` on an XObject of subtype ``/Image``), and straight paths (``m``/``l``).
That is all reportlab emits here.  It is not a general PDF parser and should
not grow into one -- if the export ever draws something this cannot see, the
gate must learn that operator rather than the export avoiding it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from pypdf import PdfReader
from pypdf.generic import ContentStream

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dixitgen.spec.units import pt_to_mm  # noqa: E402

#: PDF identity matrix, as the flat 6-tuple the ``cm`` operator uses.
IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _multiply(m: Sequence[float], n: Sequence[float]) -> Tuple[float, ...]:
    """``m`` applied first, then ``n`` -- PDF's row-vector convention."""
    a1, b1, c1, d1, e1, f1 = m
    a2, b2, c2, d2, e2, f2 = n
    return (
        a1 * a2 + b1 * c2,
        a1 * b2 + b1 * d2,
        c1 * a2 + d1 * c2,
        c1 * b2 + d1 * d2,
        e1 * a2 + f1 * c2 + e2,
        e1 * b2 + f1 * d2 + f2,
    )


def _apply(m: Sequence[float], x: float, y: float) -> Tuple[float, float]:
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


@dataclass(frozen=True)
class Placement:
    """An image drawn on the page, in millimetres, origin bottom-left."""

    name: str
    x_mm: float
    y_mm: float
    w_mm: float
    h_mm: float

    def as_tuple(self) -> Tuple[float, float, float, float]:
        return (self.x_mm, self.y_mm, self.w_mm, self.h_mm)


@dataclass(frozen=True)
class Line:
    """A straight stroke on the page, in millimetres."""

    x1_mm: float
    y1_mm: float
    x2_mm: float
    y2_mm: float


@dataclass(frozen=True)
class PageGeometry:
    index: int
    width_pt: float
    height_pt: float
    placements: List[Placement]
    lines: List[Line]


def _xobject_names(page) -> dict:
    """Map ``/Im0`` style names to their XObject subtype."""
    try:
        resources = page["/Resources"]
        xobjects = resources["/XObject"]
    except (KeyError, TypeError):
        return {}
    out = {}
    for name, ref in xobjects.items():
        try:
            out[str(name)] = str(ref.get_object().get("/Subtype", ""))
        except Exception:  # a broken XObject is not this probe's business
            out[str(name)] = ""
    return out


def page_geometry(page, index: int, reader: PdfReader) -> PageGeometry:
    """Everything drawn on one page, converted to millimetres."""
    box = page.mediabox
    width_pt = float(box.width)
    height_pt = float(box.height)

    images = _xobject_names(page)
    contents = page.get_contents()
    stream = ContentStream(contents, reader)

    ctm: Tuple[float, ...] = IDENTITY
    stack: List[Tuple[float, ...]] = []
    placements: List[Placement] = []
    lines: List[Line] = []
    current: Optional[Tuple[float, float]] = None

    for operands, operator in stream.operations:
        op = operator.decode("utf-8") if isinstance(operator, bytes) else str(operator)

        if op == "q":
            stack.append(ctm)
        elif op == "Q":
            ctm = stack.pop() if stack else IDENTITY
        elif op == "cm":
            ctm = _multiply(tuple(float(v) for v in operands), ctm)
        elif op == "Do":
            name = str(operands[0])
            if images.get(name) == "/Image":
                # An image is painted into the unit square, so the CTM's
                # scale is its size and its translation is its corner.
                x0, y0 = _apply(ctm, 0.0, 0.0)
                x1, y1 = _apply(ctm, 1.0, 1.0)
                placements.append(
                    Placement(
                        name=name,
                        x_mm=pt_to_mm(min(x0, x1)),
                        y_mm=pt_to_mm(min(y0, y1)),
                        w_mm=pt_to_mm(abs(x1 - x0)),
                        h_mm=pt_to_mm(abs(y1 - y0)),
                    )
                )
        elif op == "m" and len(operands) >= 2:
            current = _apply(ctm, float(operands[0]), float(operands[1]))
        elif op == "l" and len(operands) >= 2 and current is not None:
            end = _apply(ctm, float(operands[0]), float(operands[1]))
            lines.append(
                Line(
                    x1_mm=pt_to_mm(current[0]),
                    y1_mm=pt_to_mm(current[1]),
                    x2_mm=pt_to_mm(end[0]),
                    y2_mm=pt_to_mm(end[1]),
                )
            )
            current = end

    return PageGeometry(
        index=index,
        width_pt=width_pt,
        height_pt=height_pt,
        placements=placements,
        lines=lines,
    )


def read_pages(path: Path) -> List[PageGeometry]:
    """Every page of ``path``, as plain millimetre geometry."""
    reader = PdfReader(str(path))
    return [page_geometry(page, i, reader) for i, page in enumerate(reader.pages)]


def embedded_images(path: Path, page_index: int) -> List["object"]:
    """The **distinct** rasters embedded on one page, as PIL images.

    Distinct, not one per placement: a PDF stores a repeated image once and
    references it many times, so a back page with four identical backs holds a
    single XObject.  Use ``embedded_images_by_name`` when a placement has to
    be matched to the raster it draws.
    """
    reader = PdfReader(str(path))
    return [img.image for img in reader.pages[page_index].images]


def embedded_images_by_name(path: Path, page_index: int) -> dict:
    """``{"/Im0": <PIL image>}`` for one page.

    ``Placement.name`` is the key, so a placement parsed out of the content
    stream can be matched to the raster it actually draws -- which is the only
    way to check resolution when one image is reused across several slots.
    """
    reader = PdfReader(str(path))
    page = reader.pages[page_index]
    out = {}
    for name, subtype in _xobject_names(page).items():
        if subtype != "/Image":
            continue
        try:
            out[name] = page.images[name].image
        except Exception:
            # pypdf indexes this list by the bare name on some versions.
            out[name] = page.images[name.lstrip("/")].image
    return out
