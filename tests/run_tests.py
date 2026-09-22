"""The verify gate.  PROJECT.md names this command; nothing here is optional.

    python tests/run_tests.py > tests/last-run.txt 2>&1

What it proves, in order:

1. **The unit derivation reproduces published figures for cases we do not
   print** -- A4 in points, and an MTG card in points.  A conversion checked
   only against the numbers it was built for is unfalsifiable.
2. **The layout is what the constitution says** -- a centred 2x2 grid of
   80 x 120 mm cards on A4, bleeding outward only.
3. **The geometry assertions actually fail when they should.**  Negative
   controls, because an assertion that has never been seen to fire is a
   comment.
4. **A written PDF matches the spec** -- exported in all three duplex modes,
   then parsed back off disk and measured.  The flip mapping is checked on a
   *part-full* sheet, which is the only place it is observable: on a full
   2x2 sheet the mirrored slots occupy the same four boxes as the fronts.

Exit code 0 means every check passed.  Anything else means do not print.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import Callable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from PIL import Image  # noqa: E402

from dixitgen.export.sheet_pdf import CardArt, export_batch  # noqa: E402
from dixitgen.spec import (  # noqa: E402
    A4,
    DIXIT,
    SHEET,
    CardFormat,
    Flip,
    GeometryError,
    Segment,
    SheetLayout,
    assert_art_inside_own_slot,
    assert_clean_cards,
    assert_page_box,
    assert_placements_match_slots,
    assert_registration,
    effective_dpi,
    mm_to_pt,
    mm_to_px,
)

from pdf_probe import (  # noqa: E402
    embedded_images,
    embedded_images_by_name,
    read_pages,
)

OUT = ROOT / "out" / "verify"

#: How close a derived point value must be to the published one.  Tighter than
#: the export's own tolerance: this is arithmetic, not a drawn page.
PT_EPSILON = 1e-3


# --------------------------------------------------------------------------
# harness
# --------------------------------------------------------------------------

_RESULTS: List[Tuple[str, bool, str]] = []


def check(name: str) -> Callable:
    def decorate(fn: Callable) -> Callable:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 -- the gate reports, never crashes
            _RESULTS.append((name, False, "{}: {}".format(type(exc).__name__, exc)))
            traceback.print_exc()
        else:
            _RESULTS.append((name, True, ""))
        return fn

    return decorate


def near(got: float, want: float, eps: float, what: str) -> None:
    if abs(got - want) > eps:
        raise AssertionError(
            "{}: got {:.6f}, expected {:.6f} (differs by {:.6f}, tolerance {})".format(
                what, got, want, abs(got - want), eps
            )
        )


def equal(got, want, what: str) -> None:
    if got != want:
        raise AssertionError("{}: got {!r}, expected {!r}".format(what, got, want))


def fixture(w: int, h: int, colour: Tuple[int, int, int]) -> Image.Image:
    """A flat test image; only its size and colour matter to the geometry."""
    return Image.new("RGB", (w, h), colour)


def quadrant_fixture(w: int, h: int) -> Image.Image:
    """Four saturated quadrants, so a 180-degree rotation is visible in pixels.

    Top-left red, top-right green, bottom-left blue, bottom-right yellow.
    Rotated 180 degrees, red must end up bottom-right.
    """
    img = Image.new("RGB", (w, h), (0, 0, 0))
    half_w, half_h = w // 2, h // 2
    for box, colour in (
        ((0, 0, half_w, half_h), (255, 0, 0)),
        ((half_w, 0, w, half_h), (0, 255, 0)),
        ((0, half_h, half_w, h), (0, 0, 255)),
        ((half_w, half_h, w, h), (255, 255, 0)),
    ):
        img.paste(colour, box)
    return img


def corner_colour(img: Image.Image, corner: str) -> Tuple[int, int, int]:
    """The average colour of one corner, sampled well inside it."""
    w, h = img.size
    qx, qy = w // 4, h // 4
    x = qx if corner in ("tl", "bl") else w - qx
    y = qy if corner in ("tl", "tr") else h - qy
    patch = img.convert("RGB").crop((x - 5, y - 5, x + 5, y + 5))
    pixels = list(patch.getdata())
    n = len(pixels)
    return tuple(sum(p[i] for p in pixels) // n for i in range(3))  # type: ignore[return-value]


def colour_near(got, want, what: str, tol: int = 60) -> None:
    if any(abs(g - w) > tol for g, w in zip(got, want)):
        raise AssertionError(
            "{}: got RGB{}, expected about RGB{} (tolerance {} per channel)".format(
                what, got, want, tol
            )
        )


# --------------------------------------------------------------------------
# 1. the derivation, against figures this project does not print
# --------------------------------------------------------------------------


@check("units: A4 derives to its published PDF point size")
def _a4_points() -> None:
    near(mm_to_pt(210.0), 595.2755905511812, PT_EPSILON, "A4 width in pt")
    near(mm_to_pt(297.0), 841.8897637795277, PT_EPSILON, "A4 height in pt")
    near(A4.w_pt, 595.2755905511812, PT_EPSILON, "PaperSize A4 width")
    near(A4.h_pt, 841.8897637795277, PT_EPSILON, "PaperSize A4 height")


@check("units: an MTG card (a size we never print) derives correctly")
def _mtg_points() -> None:
    mtg = CardFormat(id="mtg", label="MTG (63 x 88 mm)", trim_w_mm=63.0, trim_h_mm=88.0)
    near(mtg.trim_w_pt, 178.58267716535433, PT_EPSILON, "MTG width in pt")
    near(mtg.trim_h_pt, 249.44881889763778, PT_EPSILON, "MTG height in pt")
    equal(mtg.trim_w_px, 744, "MTG width in px at 300dpi")
    equal(mtg.trim_h_px, 1039, "MTG height in px at 300dpi")


@check("units: the Dixit card derives to 945 x 1417 px at 300 DPI")
def _card_pixels() -> None:
    equal(DIXIT.trim_w_px, mm_to_px(80.0), "card width px")
    equal(DIXIT.trim_h_px, mm_to_px(120.0), "card height px")
    equal((DIXIT.trim_w_px, DIXIT.trim_h_px), (945, 1417), "card pixel size")
    near(DIXIT.aspect, 2.0 / 3.0, 1e-9, "card aspect")


@check("units: art at exactly the derived pixel size is not called soft")
def _soft_threshold() -> None:
    equal(DIXIT.art_is_soft(945, 1417), False, "945x1417 is exactly enough")
    equal(DIXIT.art_is_soft(944, 1417), True, "one pixel short on width is soft")
    equal(DIXIT.art_is_soft(945, 1416), True, "one pixel short on height is soft")


# --------------------------------------------------------------------------
# 2. the layout the constitution describes
# --------------------------------------------------------------------------


@check("layout: A4 holds a centred 2x2 grid with equal margins")
def _layout_shape() -> None:
    equal((SHEET.cols, SHEET.rows), (2, 2), "grid")
    equal(SHEET.cards_per_sheet, 4, "cards per sheet")
    near(SHEET.block_w_mm, 160.0, 1e-9, "block width")
    near(SHEET.block_h_mm, 240.0, 1e-9, "block height")
    near(SHEET.margin_x_mm, 25.0, 1e-9, "left/right margin")
    near(SHEET.margin_y_mm, 28.5, 1e-9, "top/bottom margin")
    # Centred both ways -- registration depends on it.
    near(
        SHEET.margin_x_mm * 2 + SHEET.block_w_mm,
        A4.w_mm,
        1e-9,
        "block centred horizontally",
    )
    near(
        SHEET.margin_y_mm * 2 + SHEET.block_h_mm,
        A4.h_mm,
        1e-9,
        "block centred vertically",
    )


@check("layout: bleed grows outward only, never onto a neighbour")
def _bleed_direction() -> None:
    assert_art_inside_own_slot(SHEET)
    top_left = SHEET.art_box(0, 0)
    card = SHEET.card_box(0, 0)
    near(card.x_mm - top_left.x_mm, SHEET.outer_bleed_mm, 1e-9, "left bleed on col 0")
    near(top_left.top_mm - card.top_mm, SHEET.outer_bleed_mm, 1e-9, "top bleed on row 0")
    near(top_left.right_mm, card.right_mm, 1e-9, "no bleed on a shared right edge")
    near(top_left.y_mm, card.y_mm, 1e-9, "no bleed on a shared bottom edge")


@check("layout: every flip registers, and crop marks stay off the cards")
def _registration_and_marks() -> None:
    for flip in Flip:
        assert_registration(SHEET, flip)
    assert_clean_cards(SHEET, SHEET.crop_marks())
    equal(len(SHEET.crop_marks()), 2 * (SHEET.cols + 1) + 2 * (SHEET.rows + 1), "marks")
    equal(SheetLayout.back_rotation_deg(Flip.LONG_EDGE), 0, "long-edge rotation")
    equal(SheetLayout.back_rotation_deg(Flip.SHORT_EDGE), 180, "short-edge rotation")
    equal(SheetLayout.back_rotation_deg(Flip.MANUAL), 0, "manual rotation")


# --------------------------------------------------------------------------
# 3. negative controls -- the assertions must be able to fail
# --------------------------------------------------------------------------


def expect_raises(exc_type, fn, what: str) -> None:
    try:
        fn()
    except exc_type:
        return
    except Exception as other:  # noqa: BLE001
        raise AssertionError(
            "{}: raised {} instead of {}".format(what, type(other).__name__, exc_type.__name__)
        )
    raise AssertionError("{}: did not raise {}".format(what, exc_type.__name__))


@check("control: an off-centre block fails registration")
def _off_centre_fails() -> None:
    class OffCentre(SheetLayout):
        @property
        def margin_x_mm(self) -> float:  # 2mm to the right of centre
            return (self.paper.w_mm - self.block_w_mm) / 2.0 + 2.0

    bad = OffCentre()
    expect_raises(
        GeometryError,
        lambda: assert_registration(bad, Flip.LONG_EDGE),
        "off-centre block under long-edge flip",
    )


@check("control: furniture drawn on a card fails the clean-card assertion")
def _dirty_card_fails() -> None:
    box = SHEET.card_box(0, 0)
    through_the_middle = Segment(
        box.x_mm + 5.0, box.y_mm + 5.0, box.right_mm - 5.0, box.top_mm - 5.0
    )
    expect_raises(
        GeometryError,
        lambda: assert_clean_cards(SHEET, [through_the_middle]),
        "a line drawn across a card",
    )


@check("control: a card too big for the paper is refused, not silently shrunk")
def _oversize_refused() -> None:
    huge = CardFormat(id="huge", label="Huge", trim_w_mm=200.0, trim_h_mm=290.0)
    expect_raises(
        ValueError, lambda: SheetLayout.fit(paper=A4, card=huge), "a 200x290mm card"
    )


@check("control: an empty selection is refused")
def _empty_batch_refused() -> None:
    expect_raises(
        ValueError,
        lambda: export_batch([], OUT / "never-written.pdf"),
        "an empty batch",
    )


# --------------------------------------------------------------------------
# 4. the written artefact
# --------------------------------------------------------------------------


def card_fixtures(n: int) -> List[CardArt]:
    palette = [
        (200, 40, 40),
        (40, 160, 90),
        (50, 90, 200),
        (220, 170, 40),
        (150, 60, 190),
    ]
    return [
        CardArt(
            name="fixture-{}".format(i),
            image=fixture(1200, 1800, palette[i % len(palette)]),
        )
        for i in range(n)
    ]


def expected_art_boxes(layout: SheetLayout, slots) -> List[Tuple[float, ...]]:
    return [layout.art_box(*slot).as_tuple() for slot in slots]


def assert_placements_are(page, boxes, what: str) -> None:
    got = sorted(p.as_tuple() for p in page.placements)
    want = sorted(boxes)
    if len(got) != len(want):
        raise AssertionError(
            "{}: page {} has {} image placements, expected {}".format(
                what, page.index, len(got), len(want)
            )
        )
    for g, w in zip(got, want):
        for axis, gv, wv in zip("xywh", g, w):
            near(gv, wv, 0.01, "{}: page {} placement {}".format(what, page.index, axis))


@check("export: a full sheet writes A4 pages with four cards and clean margins")
def _full_sheet() -> None:
    result = export_batch(
        card_fixtures(4),
        OUT / "full-long-edge.pdf",
        back=quadrant_fixture(1200, 1800),
        flip=Flip.LONG_EDGE,
    )
    equal(result.sheets, 1, "sheets")
    pages = read_pages(result.paths[0])
    equal(len(pages), 2, "pages (one front, one back)")

    all_slots = list(SHEET.slots())
    for page in pages:
        assert_page_box(page.width_pt, page.height_pt, A4)
        assert_placements_are(page, expected_art_boxes(SHEET, all_slots), "full sheet")
        assert_placements_match_slots(
            [p.as_tuple() for p in page.placements], SHEET, "art"
        )
        equal(len(page.lines), len(SHEET.crop_marks()), "crop marks on page")
        marks = [
            Segment(line.x1_mm, line.y1_mm, line.x2_mm, line.y2_mm)
            for line in page.lines
        ]
        assert_clean_cards(SHEET, marks)


@check("export: on a part-full sheet the back lands in the mirrored slot")
def _partial_sheet_shows_the_flip() -> None:
    # The only place the flip mapping is observable in the file: with four
    # cards the mirrored slots occupy the same four boxes as the fronts.
    for flip, front_slot, back_slot in (
        (Flip.LONG_EDGE, (0, 0), (0, 1)),
        (Flip.SHORT_EDGE, (0, 0), (1, 0)),
    ):
        result = export_batch(
            card_fixtures(1),
            OUT / "single-{}.pdf".format(flip.value),
            back=quadrant_fixture(1200, 1800),
            flip=flip,
        )
        pages = read_pages(result.paths[0])
        equal(len(pages), 2, "{}: pages".format(flip.value))

        assert_placements_are(
            pages[0],
            expected_art_boxes(SHEET, [front_slot]),
            "{} front".format(flip.value),
        )
        assert_placements_are(
            pages[1],
            expected_art_boxes(SHEET, [back_slot]),
            "{} back".format(flip.value),
        )
        equal(
            SHEET.back_slot(front_slot[0], front_slot[1], flip),
            back_slot,
            "{}: back slot for {}".format(flip.value, front_slot),
        )


@check("export: a short-edge back is rotated 180 degrees in the pixels")
def _short_edge_rotates_the_back() -> None:
    # Red is the top-left quadrant of the source.  Under short-edge duplex the
    # back must be turned over, so red has to come out bottom-right.
    for flip, corner in ((Flip.LONG_EDGE, "tl"), (Flip.SHORT_EDGE, "br")):
        result = export_batch(
            card_fixtures(1),
            OUT / "rotation-{}.pdf".format(flip.value),
            back=quadrant_fixture(1200, 1800),
            flip=flip,
        )
        images = embedded_images(result.paths[0], 1)
        equal(len(images), 1, "{}: one back image on the back page".format(flip.value))
        colour_near(
            corner_colour(images[0], corner),
            (255, 0, 0),
            "{}: red quadrant is {} on the printed back".format(flip.value, corner),
        )


@check("export: several sheets, with a part-full last one, back only where used")
def _multi_sheet() -> None:
    result = export_batch(
        card_fixtures(5),
        OUT / "five-cards.pdf",
        back=quadrant_fixture(1200, 1800),
        flip=Flip.LONG_EDGE,
    )
    equal(result.sheets, 2, "sheets for 5 cards at 4 per sheet")
    pages = read_pages(result.paths[0])
    equal(len(pages), 4, "pages (front+back per sheet)")
    equal(len(pages[0].placements), 4, "sheet 1 front cards")
    equal(len(pages[1].placements), 4, "sheet 1 back cards")
    equal(len(pages[2].placements), 1, "sheet 2 front cards")
    equal(
        len(pages[3].placements),
        1,
        "sheet 2 backs -- one, not four: no backs behind blank paper",
    )


@check("export: manual mode writes two files with matching page counts")
def _manual_two_files() -> None:
    result = export_batch(
        card_fixtures(5),
        OUT / "manual.pdf",
        back=quadrant_fixture(1200, 1800),
        flip=Flip.MANUAL,
    )
    equal(len(result.paths), 2, "files written")
    fronts, backs = result.paths
    equal(fronts.name, "manual.fronts.pdf", "fronts filename")
    equal(backs.name, "manual.backs.pdf", "backs filename")
    front_pages, back_pages = read_pages(fronts), read_pages(backs)
    equal(len(front_pages), 2, "front pages")
    equal(len(back_pages), 2, "back pages")
    for page in front_pages + back_pages:
        assert_page_box(page.width_pt, page.height_pt, A4)


@check("export: every placed raster resolves at 300 DPI or better")
def _resolution_of_written_rasters() -> None:
    path = OUT / "full-long-edge.pdf"
    pages = read_pages(path)
    for page in pages:
        # By name, not by index: a PDF stores one XObject for a repeated image,
        # so the back page's four identical backs share a single raster.  The
        # placement carries the name it draws, which is what pairs them.
        rasters = embedded_images_by_name(path, page.index)
        for placement in page.placements:
            if placement.name not in rasters:
                raise AssertionError(
                    "page {}: placement draws {} but the page has no such "
                    "image XObject (has {})".format(
                        page.index, placement.name, sorted(rasters)
                    )
                )
            img = rasters[placement.name]
            dpi_x = effective_dpi(img.size[0], placement.w_mm)
            dpi_y = effective_dpi(img.size[1], placement.h_mm)
            if min(dpi_x, dpi_y) < DIXIT.dpi:
                raise AssertionError(
                    "page {}: raster {}x{}px placed across {:.2f}x{:.2f}mm "
                    "resolves at {:.0f}x{:.0f} DPI, below {}".format(
                        page.index,
                        img.size[0],
                        img.size[1],
                        placement.w_mm,
                        placement.h_mm,
                        dpi_x,
                        dpi_y,
                        DIXIT.dpi,
                    )
                )


@check("export: low-resolution art warns but still exports")
def _low_res_warns_not_blocks() -> None:
    small = [CardArt(name="tiny", image=fixture(300, 450, (120, 120, 120)))]
    result = export_batch(small, OUT / "low-res.pdf", flip=Flip.LONG_EDGE)
    equal(len(result.paths), 1, "the export still produced a file")
    if not result.warnings:
        raise AssertionError(
            "300x450px art across an 83x123mm box should warn, got no warnings"
        )
    if "soft" not in result.warnings[0]:
        raise AssertionError(
            "warning should say the art will look soft, got: {}".format(
                result.warnings[0]
            )
        )


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------


def main() -> int:
    passed = [r for r in _RESULTS if r[1]]
    failed = [r for r in _RESULTS if not r[1]]

    print("DixitGenerator verify gate")
    print("=" * 72)
    print("card   : {} -> {} x {} px at {} DPI".format(
        DIXIT.label, DIXIT.trim_w_px, DIXIT.trim_h_px, DIXIT.dpi))
    print("sheet  : {}, {}x{} grid, {} cards/sheet, margins {}/{} mm".format(
        SHEET.paper.label, SHEET.cols, SHEET.rows, SHEET.cards_per_sheet,
        SHEET.margin_x_mm, SHEET.margin_y_mm))
    print("output : {}".format(OUT))
    print("=" * 72)

    for name, ok, detail in _RESULTS:
        print("{} {}".format("PASS" if ok else "FAIL", name))
        if detail:
            print("     {}".format(detail))

    print("=" * 72)
    print("{} passed, {} failed, {} total".format(len(passed), len(failed), len(_RESULTS)))
    if failed:
        print("DO NOT PRINT -- the geometry does not match the spec.")
        return 1
    print("Geometry matches the spec. Safe to print.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
