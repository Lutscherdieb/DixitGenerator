# DixitGenerator — architecture

## Overview

One direction of flow, four stages, and a single owner for every number:

```
  upload ──▶ store ──▶ overview ──▶ export ──▶ A4 PDF ──▶ printer ──▶ guillotine
             (sqlite)  (browser)   (reportlab)

                    ┌─────────────────────────┐
                    │  dixitgen.spec          │  every measurement lives here
                    │  units · card · sheet   │  and nowhere else
                    │  verify                 │
                    └─────────────────────────┘
                       ▲        ▲         ▲
                   /api/meta  export   verify gate
                   (browser)          (asserts the written PDF)
```

The rule that shapes everything: **`dixitgen.spec` owns every millimetre, point
and pixel.** The browser gets them over `/api/meta`, the export asks the objects
directly, and `tools/check_geometry_literals.py` fails if any of them is typed a
second time anywhere else.

The second rule, from PROJECT.md: **the card is the image.** No module draws
text, a border or a frame inside a card box, and `assert_clean_cards` is what
holds that, rather than discipline.

## Components

### `dixitgen.spec` — the measurements

| Module | Owns |
|---|---|
| `units.py` | `mm ↔ pt ↔ px`, the tolerances, and the published ratios they come from |
| `card.py` | `CardFormat`; `DIXIT` is 80 × 120 mm, deriving to 945 × 1417 px at 300 DPI |
| `sheet.py` | `PaperSize`, `SheetLayout`, `Rect`, `Segment`, `Flip`: the grid, the bleed, the crop marks, the duplex mapping |
| `verify.py` | The assertions the export and the gate both call |

`SheetLayout.fit()` *derives* the grid from the paper and the card rather than
storing `cols=2, rows=2`, so a new paper size is a data change. On A4 that
derivation gives a 2 × 2 block of 160 × 240 mm with 25 / 28.5 mm margins.

`spec.as_dict()` is the one serialisation and `/api/meta` its only consumer —
that is how the frontend stays free of measurements.

### `dixitgen.render` — crop-to-fill

`crop_to_fill` takes the largest correctly-shaped crop of a source image.
`focus` is a point in 0..1 of the source that the crop window centres on; it is
the per-card nudge, stored as two numbers rather than a pixel rectangle so it
survives a re-upload at a different resolution.

The crop does **not** resample to a pixel size. The PDF places the image at a
size in millimetres and the raster goes in at whatever resolution it has, which
is what keeps a high-resolution source high-resolution.

### `dixitgen.export` — batch to PDF

`export_batch` chunks the selection into sheets, draws each front page, and —
for each *used* slot only — draws the chosen back into the mirrored slot.
Auto-duplex modes interleave front/back pages in one file; `Flip.MANUAL` writes
`<name>.fronts.pdf` and `<name>.backs.pdf`.

Every geometry assertion runs **before** the canvas is created, so a batch that
would not register produces no file at all.

### `dixitgen.web` + `web/` — the overview

CherryPy serves JSON under `/api` and the static client under `/web`. The client
is plain ES modules, no build step. **8775 is the author's port, 8776 is a
throwaway** — the split is in CLAUDE.md and exists so that stopping one can
never take the other down.

### `tests/` — the gate

`pdf_probe.py` reads a written PDF back into plain millimetres: it walks the
content stream, tracks the graphics-state stack and the CTM, and reports image
placements and stroked lines. `run_tests.py` uses it to check the **file**, not
the layout object that produced it.

## Decisions & reversals

### The block is centred, and that is what makes duplex work

With the block centred on the paper, the mirror of a front slot about the page's
centre line *is* another slot of the same grid, exactly. So the duplex mapping is
a permutation of slots (`col → cols-1-col` for long-edge, `row → rows-1-row` for
short-edge) and needs no measured offset. An off-centre block would pair the
slots up correctly and still misregister on paper — which is why
`assert_registration` checks the geometry as well as the permutation, and why the
gate keeps a deliberately off-centre layout as a negative control.

### Cards touch; only the block's outer edge gets bleed

Adjacent cards share a cut line, so one guillotine pass serves two cards and an
off-by-1 mm cut still leaves both full-bleed — one 81 mm, its neighbour 79 mm,
neither showing white. A gutter would turn the same error into a white sliver,
which is the failure people actually see on a laminated card.

The block's outer edges have no neighbour to borrow from, so `art_box` grows
those sides by `outer_bleed_mm` (3 mm) and only those.

### The flip mapping is only observable on a part-full sheet

On a full 2 × 2 sheet the mirrored slots occupy the *same four boxes* as the
fronts, so a four-card test passes no matter which flip the code applied. The
gate therefore checks the mapping with a **one-card** batch, where long-edge puts
the back in slot (0,1) and short-edge in (1,0). Any future registration test must
keep a part-full fixture for the same reason.

### Short-edge duplex also rotates the back image 180°

A person turns a card about its vertical axis. Under short-edge duplex the back
arrives mirrored top-to-bottom, so without the rotation the back reads upside
down on the cut card. This is invisible on a symmetric back design, which is
exactly why the gate checks it in the **pixels** — a quadrant-coloured fixture
whose red corner must come out bottom-right.

### Compare pixel counts, not computed DPI, for the soft-art warning

Art at exactly the derived size (945 × 1417) resolves at 299.93 DPI on the long
axis, because 1417 is the *rounded* pixel count. A float comparison against 300
therefore calls the exactly-right image soft. `CardFormat.art_is_soft` compares
against `mm_to_px` instead, which is exact and matches how the threshold is
described to the user.

### A measurement in a comment is prose, not a source of truth

`check_geometry_literals.py` strips comments and Python docstrings before
scanning, so a comment explaining that the card is 80 mm wide is not a finding
while `const CARD_W = "80mm"` is. Without that, the checker's own docstring
failed the checker — and a tool that cries wolf trains people to ignore it.

### A repeated image is one XObject, not one per placement

A PDF stores a reused image once and references it many times, so a back page
with four identical backs holds a **single** raster. Any check that pairs a
placement with its pixels must look the XObject up by the name the placement
carries; counting `page.images` against placements fails on exactly the page that
matters most.

### No rounded corners in the PDF

Dixit cards have rounded corners; a guillotine cuts square ones. A corner punch
after lamination is the intended finish. A printed radius that is then cut square
looks worse than no radius at all, so the export deliberately draws none.

### reportlab, not Pillow, for the PDF

Pillow can emit a multi-page PDF but gives no control over where on the page
anything lands, and cannot draw a vector crop mark. Exact millimetre placement is
the entire product here, so the heavier dependency is the right trade.
