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

import hashlib
import io
import sys
import traceback
from pathlib import Path
from typing import Callable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from PIL import Image  # noqa: E402

from dixitgen import store  # noqa: E402
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
    assert_placements_cover_cards,
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


def band_fixture(w: int, h: int) -> Image.Image:
    """Three equal vertical bands: red, green, blue, left to right.

    For checking a horizontal crop.  The quadrant fixture is wrong for that
    job: cropping a square to 2:3 keeps two thirds of the width, so a corner
    sampled at 1/4 and 3/4 of the crop lands exactly on the quadrant seam and
    reads as a red/green blend.  Bands at thirds put every sample point well
    inside one colour.
    """
    img = Image.new("RGB", (w, h), (0, 0, 0))
    third = w // 3
    for i, colour in enumerate(((255, 0, 0), (0, 255, 0), (0, 0, 255))):
        img.paste(colour, (i * third, 0, (i + 1) * third if i < 2 else w, h))
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


def assert_placements_are(page, slots, what: str) -> None:
    """Every named slot is framed by exactly one placement on this page."""
    assert_placements_cover_cards(
        [p.as_tuple() for p in page.placements], SHEET, list(slots), what
    )


def trim_crop(img: Image.Image) -> Image.Image:
    """What the preview shows, and what a cut card must show."""
    from dixitgen.render.crop import crop_to_fill

    return crop_to_fill(img, DIXIT.trim_w_mm, DIXIT.trim_h_mm)


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
        assert_placements_are(page, all_slots, "full sheet")
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

        assert_placements_are(pages[0], [front_slot], "{} front".format(flip.value))
        assert_placements_are(pages[1], [back_slot], "{} back".format(flip.value))
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


@check("export: progress is reported once per card drawn, and reaches the total")
def _progress_is_real() -> None:
    # The overview shows this number, so it has to mean something: one tick per
    # image actually placed, monotonic, ending exactly at the total.
    seen = []
    cards = [CardArt(name="p{}".format(i), image=band_fixture(900, 1350)) for i in range(5)]
    export_batch(
        cards,
        OUT / "progress.pdf",
        back=band_fixture(900, 1350),
        flip=Flip.LONG_EDGE,
        progress=lambda done, total: seen.append((done, total)),
    )
    equal(seen[0], (0, 10), "first report is zero of the total")
    equal(seen[-1], (10, 10), "last report reaches the total")
    equal([d for d, _ in seen], list(range(11)), "one tick per image, in order")
    equal({t for _, t in seen}, {10}, "the total never changes mid-run")


@check("export: a back's own crop focus reaches the PDF")
def _back_focus_is_honoured() -> None:
    # A back is re-framed in the same editor as a card, so its focus has to
    # travel the same distance -- into the actual raster, not just the shelf.
    source = band_fixture(1400, 1400)  # square: real horizontal crop freedom
    rasters = {}
    for focus in ((0.0, 0.5), (1.0, 0.5)):
        result = export_batch(
            [CardArt(name="front", image=band_fixture(1200, 1800))],
            OUT / "back-focus-{}.pdf".format(focus[0]),
            back=source,
            flip=Flip.LONG_EDGE,
            back_focus=focus,
        )
        images = embedded_images(result.paths[0], 1)
        equal(len(images), 1, "one back raster")
        rasters[focus] = corner_colour(images[0], "tl")

    # Keeping the source's left third shows red; keeping the right third shows
    # green, since a square cropped to 2:3 keeps two thirds of the width.
    colour_near(rasters[(0.0, 0.5)], (255, 0, 0), "back focus 0 keeps the left band")
    colour_near(rasters[(1.0, 0.5)], (0, 255, 0), "back focus 1 moves the window right")


# --------------------------------------------------------------------------
# 5. the card library
# --------------------------------------------------------------------------

SCRATCH_DB = OUT / "scratch-library.db"


def png_bytes(img: Image.Image) -> bytes:
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


_LAST_ENGINE = []


def scratch_engine():
    """A throwaway database, fresh for each check.

    The gate must never touch the author's library: these checks add, mutate
    and delete rows, and `data/cards.db` holds the only copy of every image.

    ``dispose()`` before ``unlink()`` is not optional on Windows. SQLAlchemy
    keeps pooled SQLite connections open, and an open handle makes the file
    undeletable -- every check after the first died with
    ``PermissionError: [WinError 32] The process cannot access the file
    because it is being used by another process``.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    while _LAST_ENGINE:
        _LAST_ENGINE.pop().dispose()
    if SCRATCH_DB.exists():
        SCRATCH_DB.unlink()
    engine = store.make_engine("sqlite:///{}".format(SCRATCH_DB.as_posix()))
    _LAST_ENGINE.append(engine)
    return engine


@check("store: the gate runs against a scratch database, never the library")
def _scratch_is_not_the_library() -> None:
    url = "sqlite:///{}".format(SCRATCH_DB.as_posix())
    equal(store.database_url(url), url, "explicit url wins")
    if store.DEFAULT_DB_PATH.as_posix() in url:
        raise AssertionError(
            "the scratch database resolves to the author's library at {}".format(
                store.DEFAULT_DB_PATH
            )
        )


@check("store: an upload round-trips byte-identically")
def _bytes_round_trip() -> None:
    original = png_bytes(quadrant_fixture(1200, 1800))
    engine = scratch_engine()
    with store.session_scope(engine) as session:
        card = store.add_card(session, original, name="round trip")
        card_id = card.id
    with store.session_scope(engine) as session:
        again = store.get_card(session, card_id)
        equal(again.image, original, "stored bytes")
        equal(
            hashlib.sha256(again.image).hexdigest(),
            again.image_sha256,
            "recorded content hash",
        )


@check("store: derived fields are computed from the bytes, not taken on trust")
def _derived_fields() -> None:
    engine = scratch_engine()
    with store.session_scope(engine) as session:
        card = store.add_card(session, png_bytes(fixture(1234, 987, (10, 20, 30))))
        equal((card.src_w, card.src_h), (1234, 987), "cached source size")
        equal(card.image_mime, "image/png", "sniffed mime")
        equal((card.focus_x, card.focus_y), (0.5, 0.5), "default focus")
        if not card.thumb:
            raise AssertionError("no thumbnail was generated on upload")
        if len(card.thumb) >= len(card.image):
            raise AssertionError(
                "thumbnail ({} bytes) is not smaller than the source "
                "({} bytes)".format(len(card.thumb), len(card.image))
            )


@check("store: a thumbnail is cropped to the card's shape, not the source's")
def _thumb_shows_the_print_crop() -> None:
    engine = scratch_engine()
    with store.session_scope(engine) as session:
        # A square source cannot be 2:3; the tile must show the crop that will
        # print, or you choose a card in the grid and meet its crop at the
        # guillotine.
        card = store.add_card(session, png_bytes(fixture(1000, 1000, (90, 30, 30))))
        with Image.open(io.BytesIO(card.thumb)) as tile:
            tile_aspect = tile.size[0] / tile.size[1]
        near(tile_aspect, DIXIT.aspect, 0.01, "thumbnail aspect vs card aspect")


@check("store: changing the focus regenerates the thumbnail")
def _focus_change_regenerates_thumb() -> None:
    engine = scratch_engine()
    with store.session_scope(engine) as session:
        # A SQUARE source, deliberately.  A 2:3 source is already the card's
        # shape, so the crop window fills it and no focus can move it -- a
        # fixture with no degrees of freedom cannot observe the thing under
        # test.  (Same trap as the part-full-sheet rule for the flip mapping.)
        card = store.add_card(session, png_bytes(band_fixture(1200, 1200)))
        card_id, before = card.id, card.thumb
        left = store.set_focus(session, card_id, (0.0, 0.5))
        equal((left.focus_x, left.focus_y), (0.0, 0.5), "stored focus")
        if left.thumb == before:
            raise AssertionError(
                "focus moved from (0.5, 0.5) to (0.0, 0.5) on a square source "
                "but the thumbnail bytes are unchanged -- the grid would show "
                "the old crop"
            )
        # Cropping a square to 2:3 keeps two thirds of the width.  At focus 0
        # that is the red and green bands; at focus 1, green and blue.
        with Image.open(io.BytesIO(left.thumb)) as tile:
            colour_near(corner_colour(tile, "tl"), (255, 0, 0), "focus 0: left band")
            colour_near(corner_colour(tile, "tr"), (0, 255, 0), "focus 0: right band")

        right = store.set_focus(session, card_id, (1.0, 0.5))
        with Image.open(io.BytesIO(right.thumb)) as tile:
            colour_near(corner_colour(tile, "tl"), (0, 255, 0), "focus 1: left band")
            colour_near(corner_colour(tile, "tr"), (0, 0, 255), "focus 1: right band")

        # Clamped, not raising: a focus carried over from a differently-shaped
        # earlier upload degrades to "as close as this image allows".
        clamped = store.set_focus(session, card_id, (5.0, -3.0))
        equal((clamped.focus_x, clamped.focus_y), (1.0, 0.0), "clamped focus")


@check("store: a source already at the card's aspect has no crop to nudge")
def _no_crop_freedom_is_not_a_bug() -> None:
    # The complement of the check above, asserted so nobody "fixes" it: a 2:3
    # source fills the card exactly, so every focus produces the same tile.
    # This is correct behaviour, and it is why the check above uses a square.
    engine = scratch_engine()
    with store.session_scope(engine) as session:
        card = store.add_card(session, png_bytes(quadrant_fixture(1200, 1800)))
        card_id, before = card.id, card.thumb
        moved = store.set_focus(session, card_id, (0.0, 1.0))
        equal((moved.focus_x, moved.focus_y), (0.0, 1.0), "focus is still stored")
        equal(moved.thumb, before, "tile is unchanged, because nothing is cropped")


@check("store: tags normalise, de-duplicate and filter")
def _tags() -> None:
    engine = scratch_engine()
    equal(store.normalise_tag("  Deck  1 "), "deck 1", "tag normalisation")
    with store.session_scope(engine) as session:
        a = store.add_card(
            session, png_bytes(fixture(900, 1350, (1, 2, 3))), name="a",
            tags=["Surreal", " surreal ", "SURREAL", "deck 1"],
        )
        store.add_card(
            session, png_bytes(fixture(900, 1350, (4, 5, 6))), name="b",
            tags=["deck 1"],
        )
        store.add_card(session, png_bytes(fixture(900, 1350, (7, 8, 9))), name="c")

        equal(sorted(t.name for t in a.tags), ["deck 1", "surreal"], "deduped tags")
        equal(len(store.list_cards(session, tag="Deck 1")), 2, "filter by tag")
        equal(len(store.list_cards(session, tag="surreal")), 1, "filter by tag")
        equal(len(store.list_cards(session)), 3, "unfiltered listing")
        equal(dict(store.all_tags(session))["deck 1"], 2, "tag usage count")
        equal(len(store.list_cards(session, search="b")), 1, "search by name")


@check("store: a bad upload is refused at upload time, not at print time")
def _bad_upload_refused() -> None:
    engine = scratch_engine()
    with store.session_scope(engine) as session:
        expect_raises(
            store.StoreError,
            lambda: store.add_card(session, b"this is not an image"),
            "a non-image upload",
        )
        expect_raises(
            store.StoreError,
            lambda: store.add_card(session, b""),
            "an empty upload",
        )
        expect_raises(
            store.StoreError, lambda: store.get_card(session, 9999), "a missing id"
        )


@check("store: duplicate content is reported, not blocked")
def _duplicate_detection() -> None:
    engine = scratch_engine()
    data = png_bytes(fixture(900, 1350, (33, 99, 66)))
    with store.session_scope(engine) as session:
        equal(store.find_by_content(session, data), [], "nothing before the upload")
        store.add_card(session, data, name="first")
        equal(len(store.find_by_content(session, data)), 1, "found after upload")
        # Re-using one picture for two cards is legitimate and must still work.
        store.add_card(session, data, name="second")
        equal(len(store.find_by_content(session, data)), 2, "duplicate allowed")


@check("store: delete is permanent and removes the row")
def _delete_is_permanent() -> None:
    engine = scratch_engine()
    with store.session_scope(engine) as session:
        card = store.add_card(session, png_bytes(fixture(900, 1350, (5, 5, 5))))
        card_id = card.id
        store.delete_card(session, card_id)
    with store.session_scope(engine) as session:
        equal(len(store.list_cards(session)), 0, "listing after delete")
        expect_raises(
            store.StoreError,
            lambda: store.get_card(session, card_id),
            "fetching a deleted card",
        )


@check("store -> export: a selection exports in the order it was made")
def _selection_order_is_preserved() -> None:
    engine = scratch_engine()
    with store.session_scope(engine) as session:
        ids = [
            store.add_card(
                session, png_bytes(fixture(900, 1350, (i * 20, 0, 0))),
                name="card-{}".format(i),
            ).id
            for i in range(4)
        ]
        picked = [ids[2], ids[0], ids[3]]
        batch = store.batch_for_export(session, picked)
        equal(
            [art.name for art in batch],
            ["card-2", "card-0", "card-3"],
            "batch order follows the selection, not the database",
        )


@check("store -> export: the library's pixels reach the PDF unresampled")
def _library_bytes_reach_the_pdf() -> None:
    engine = scratch_engine()
    source = quadrant_fixture(1200, 1800)  # already 2:3: no spare pixels to bleed
    with store.session_scope(engine) as session:
        card = store.add_card(session, png_bytes(source), name="through-the-store")
        back = store.add_back(session, png_bytes(quadrant_fixture(1200, 1800)))
        batch = store.batch_for_export(session, [card.id])
        result = export_batch(
            batch,
            OUT / "from-store.pdf",
            back=store.to_back_image(back),
            flip=Flip.LONG_EDGE,
        )

    pages = read_pages(result.paths[0])
    equal(len(pages), 2, "pages")
    rasters = embedded_images_by_name(result.paths[0], 0)
    equal(len(rasters), 1, "one front raster")
    placed = list(rasters.values())[0]

    # A 2:3 source is exactly the card's shape, so the trim crop is the whole
    # image and there is not one spare pixel to bleed with.  The raster must
    # therefore arrive whole -- any other size means something resampled or,
    # worse, that the trim line is eating into the picture.
    equal(placed.size, source.size, "raster size vs uploaded size")
    box = pages[0].placements[0]
    near(box.w_mm, DIXIT.trim_w_mm, 0.01, "drawn width with no bleed available")
    near(box.h_mm, DIXIT.trim_h_mm, 0.01, "drawn height with no bleed available")

    # And the pixels are the uploaded ones, not something re-generated.
    colour_near(
        corner_colour(placed, "tl"), (255, 0, 0), "top-left quadrant survived the store"
    )
    colour_near(
        corner_colour(placed, "tr"), (0, 255, 0), "top-right quadrant survived the store"
    )


def slot_of(placement, layout: SheetLayout = None) -> Tuple[int, int]:
    """The slot whose card box this placement frames."""
    layout = layout or SHEET
    for slot in layout.slots():
        card = layout.card_box(*slot)
        if (
            placement.x_mm <= card.x_mm + 0.01
            and placement.y_mm <= card.y_mm + 0.01
            and placement.x_mm + placement.w_mm >= card.right_mm - 0.01
            and placement.y_mm + placement.h_mm >= card.top_mm - 0.01
        ):
            return slot
    raise AssertionError(
        "placement ({:.2f}, {:.2f}) {:.2f}x{:.2f}mm frames no card box".format(
            placement.x_mm, placement.y_mm, placement.w_mm, placement.h_mm
        )
    )


@check("export: the cut card shows the preview's crop, identically in every slot")
def _trim_framing_is_slot_independent() -> None:
    # The regression guard for the bug the author found on a real export
    # (2026-09-23): art was scaled to fill the BLED box, so the trim line cut
    # into the picture -- and because bleed exists only on the block's outer
    # edges, slot (0,0) lost its left and top while slot (1,1) lost its right
    # and bottom.  The same card printed differently depending on where it
    # landed on the sheet.
    #
    # 928x1232 is the author's own source shape: wider than the card, so a
    # bleeding layout has material to take.  The invariant must hold whether
    # bleed is off (the default) or on, so both are exercised.
    source = band_fixture(928, 1232)
    preview = trim_crop(source)

    for label, layout in (
        ("bleed off", SHEET),
        ("bleed 3mm", SheetLayout.fit(outer_bleed_mm=3.0)),
    ):
        cards = [CardArt(name="same-{}".format(i), image=source) for i in range(4)]
        result = export_batch(
            cards,
            OUT / "trim-framing-{}.pdf".format(layout.outer_bleed_mm),
            layout=layout,
            flip=Flip.LONG_EDGE,
        )
        page = read_pages(result.paths[0])[0]
        rasters = embedded_images_by_name(result.paths[0], 0)
        equal(len(page.placements), 4, "{}: placements".format(label))

        trims = set()
        for placement in page.placements:
            card = layout.card_box(*slot_of(placement, layout))
            raster = rasters[placement.name]
            trims.add(
                (
                    round(card.w_mm * raster.size[0] / placement.w_mm),
                    round(card.h_mm * raster.size[1] / placement.h_mm),
                )
            )

        if len(trims) != 1:
            raise AssertionError(
                "{}: the same card is framed differently depending on its slot: "
                "trim regions {}".format(label, sorted(trims))
            )
        got = trims.pop()
        if abs(got[0] - preview.size[0]) > 1 or abs(got[1] - preview.size[1]) > 1:
            raise AssertionError(
                "{}: the cut card would show {}x{}px of the source but the "
                "preview shows {}x{}px -- the trim line is eating into the "
                "picture".format(label, got[0], got[1], preview.size[0], preview.size[1])
            )


@check("export: with bleed off, every drawn box is exactly its card box")
def _no_bleed_by_default() -> None:
    # The author's decision, 2026-09-23: no bleed, cut the outer border
    # cleanly. Nothing may be drawn outside the cut line, for any source shape
    # -- including one with plenty of spare pixels sideways.
    equal(SHEET.outer_bleed_mm, 0.0, "default bleed")
    for name, (w, h) in (
        ("exactly 2:3", (1200, 1800)),
        ("wider than the card", (928, 1232)),
        ("square", (1400, 1400)),
        ("much wider", (3000, 2000)),
    ):
        cards = [CardArt(name=name, image=band_fixture(w, h)) for _ in range(4)]
        result = export_batch(
            cards, OUT / "no-bleed-{}x{}.pdf".format(w, h), flip=Flip.LONG_EDGE
        )
        page = read_pages(result.paths[0])[0]
        equal(len(page.placements), 4, "{}: placements".format(name))
        for placement in page.placements:
            card = SHEET.card_box(*slot_of(placement, SHEET))
            for axis, got, want in (
                ("x", placement.x_mm, card.x_mm),
                ("y", placement.y_mm, card.y_mm),
                ("width", placement.w_mm, card.w_mm),
                ("height", placement.h_mm, card.h_mm),
            ):
                near(got, want, 0.01, "{} ({}x{}): drawn {}".format(name, w, h, axis))


@check("export: bleed still works when switched back on")
def _bleed_machinery_still_works() -> None:
    # The bleed code is kept rather than deleted, so it stays proven: raise
    # outer_bleed_mm and the outer edges must grow, using source pixels from
    # outside the trim crop.
    layout = SheetLayout.fit(outer_bleed_mm=3.0)
    cards = [CardArt(name="bleeder", image=band_fixture(928, 1232)) for _ in range(4)]
    result = export_batch(
        cards, OUT / "bleed-on.pdf", layout=layout, flip=Flip.LONG_EDGE
    )
    page = read_pages(result.paths[0])[0]
    grew = 0
    for placement in page.placements:
        card = layout.card_box(*slot_of(placement, layout))
        left = card.x_mm - placement.x_mm
        right = (placement.x_mm + placement.w_mm) - card.right_mm
        if left > 0.01 or right > 0.01:
            grew += 1
        # crop_to_fill always uses 100% of one axis, so that axis never has a
        # spare pixel: this source is wider than the card, so top and bottom
        # can never bleed however large the setting.
        near(placement.h_mm, card.h_mm, 0.01, "no vertical bleed is available")
    equal(grew, 4, "outer columns took their sideways bleed")


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
