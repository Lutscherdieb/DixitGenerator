# DixitGenerator — architecture

## Overview

One direction of flow, four stages, and a single owner for every number:

```
  upload ──▶ store ──▶ overview ──▶ export ─┬▶ A4 PDF ─▶ printer ─▶ guillotine
             (sqlite)  (browser)            │  (reportlab)
                                            └▶ per-card PNGs in a zip
                                               (press-ready, or plain crops)

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

The third, added 2026-09-23 when the export grew a second writer: **one crop
serves every output.** A card is framed once, by its trim rectangle; a press's
bleed is added *outside* that framing. See "One framing, three outputs" below —
it is the invariant that makes a card ordered from a press and a card cut off an
A4 sheet the same picture.

## Components

### `dixitgen.spec` — the measurements

| Module | Owns |
|---|---|
| `units.py` | `mm ↔ pt ↔ px`, the tolerances, and the published ratios they come from |
| `card.py` | `CardFormat`; `DIXIT` is 80 × 120 mm, deriving to 945 × 1417 px at 300 DPI. `TAROT_MPC` is a size we do **not** print — see `press.py` |
| `press.py` | `PressFormat`: a card format plus a print service's mandatory bleed, and the only place a press number lives |
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

### `dixitgen.store` — the card library

One SQLite file, `data/cards.db`, holding the **image bytes themselves**. Copy
that file and you have copied the library.

| Table | Holds |
|---|---|
| `cards` | name, notes, the upload's bytes, its source size, the crop focus, a thumbnail, a content hash |
| `backs` | the same image columns (via `ImageMixin`), plus a name |
| `tags` + `card_tags` | free labels, normalised, many-to-many |

`repo.py` is the only door. It exists to hold two invariants that a bare model
cannot:

- **Derived fields have exactly one writer.** `_apply_image` computes
  `src_w`/`src_h`, the MIME type, the thumbnail and the SHA-256 from the bytes
  on the way in. `set_focus` is a function rather than a field assignment
  *because* it must regenerate the thumbnail — a focus changed without a new
  tile leaves the grid showing a crop the PDF will not produce.
- **Tags are normalised at one chokepoint.** `normalise_tag` trims, collapses
  inner whitespace and lowercases, so `"Deck 1"`, `" deck  1 "` and `"DECK 1"`
  are one tag. Without it, "select everything in deck 1" silently returns half
  the deck.

`batch_for_export` is the bridge: it returns `CardArt` objects in **the
caller's order**, because a batch is a selection in the order you made it, not
in database order.

### `dixitgen.export` — batch to sheets, or to per-card files

| Module | Writes |
|---|---|
| `formats.py` | The menu: `a4-pdf`, `mpc-dixit`, `crops`. Labels and figures derived from the spec objects, served to the browser through `/api/meta` |
| `sheet_pdf.py` | `export_batch` — A4 duplex sheets |
| `card_images.py` | `export_card_images` — one PNG per card, zipped |

`export_batch` chunks the selection into sheets, draws each front page, and —
for each *used* slot only — draws the chosen back into the mirrored slot.
Auto-duplex modes interleave front/back pages in one file; `Flip.MANUAL` writes
`<name>.fronts.pdf` and `<name>.backs.pdf`.

Every geometry assertion runs **before** the canvas is created, so a batch that
would not register produces no file at all.

`export_card_images` writes one `NNN-name.png` per card plus a single
`back.png`, into one `.zip`. It lays nothing out on paper, so it runs no
registration assertion, reports `sheets=0` and `flip=None`, and the dialog hides
the duplex and calibration controls for it. For a press format it also drops a
`README-<press>.txt` into the archive carrying the upload size and the ordering
caveat, every figure read off the spec object so it cannot drift from the files
beside it.

**Adding a format is one entry in `formats.py`.** The dialog, `/api/meta` and
the download MIME table all derive from it; `api.py` asserts at import that
every format's suffix is one it can serve, so "added a format, forgot its media
type" fails on startup rather than as a 404 after a long export.

### `dixitgen.web` + `web/` — the overview

CherryPy serves JSON under `/api` and the static client under `/web`. **8775 is
the author's port, 8776 is a throwaway** — the split is in CLAUDE.md and exists
so that stopping one can never take the other down.

`/api/meta` also reports `is_default_library`: a boolean saying whether this
server is serving the real `data/cards.db`. `tests/check_gallery.py` uploads,
edits and **deletes**, so it refuses to run when that is true. A boolean, not a
path — the guard needs no filesystem detail.

**Cards and backs are the same kind of resource** — an image with a name and a
crop focus — so the API verbs are generic over a `kind` of `cards` or `backs`,
and one editor serves both. A back simply has no tags and no notes.

**Export is a background job.** `POST /api/export` validates the selection,
starts a worker thread and returns `202` with a job id; the client polls
`/api/export/status/<id>`. A deck of eighty cards is eighty large rasters
cropped and embedded, and holding the request open for that with nothing to show
is the wrong shape. The progress number is honest — `export_batch` calls back
once per image actually placed — rather than an animation timed to finish when
the request does. The worker opens its **own** session, because a SQLAlchemy
session is not thread-safe.

The client is plain ES modules, no build step, acyclic by construction:

```
  api.js ◀─┐
  dom.js ◀─┼── toast.js ◀── grid / editor / upload / backs / exporter ◀── app.js
  state.js ◀┘
```

`app.js` is the only module that imports all the others. It sets
`document.body.dataset.ready` when the first load completes — an explicit
readiness signal, because `#grid` and `#spec-line` both exist in the static HTML
and a test that waits for *them* races the fetches.

Notifications (`toast.js`) are pinned to the **viewport**, stack, and each
carries its own dismiss button; the container draws nothing of its own, so with
no messages the page is completely clear. A toast can be updated in place, which
is how one notification goes from `Exporting… 40%` to `Batch exported` with its
Download and Open links rather than piling up a line per poll. Those two are
real `<a>` elements, not buttons, so right-click, middle-click and "save as" all
work without any JavaScript.

Selection is an **ordered list**, not a `Set`: an export batch is a selection in
the order you made it, the tile badges show that order, and
`store.list_cards(ids=…)` preserves it server-side. A `Set` would silently
reorder the printed deck.

### `tests/` — two checks, deliberately separate

`run_tests.py` is the verify gate: geometry, the store, and PDFs parsed back off
disk. `pdf_probe.py` does that parsing — it walks the content stream, tracks the
graphics-state stack and the CTM, and reports image placements and stroked
lines, so the gate checks the **file** rather than the layout object that
produced it.

`check_gallery.py` drives real Chromium against a running server, through both
export kinds — the PDF with its Download/Open pair, and an image format whose
zip it downloads and opens to count the files. It is not part of the gate and
`web/**` is not in `source_globs`, because exporting a PDF proves nothing about
the browser. It earns that separation: it caught a POST that a
redirect was silently turning into a GET, which no amount of PDF measuring could
have seen.

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
off-by-1 mm cut still leaves both full-bleed - one 81 mm, its neighbour 79 mm,
neither showing white. A gutter would turn the same error into a white sliver,
which is the failure people actually see on a laminated card.

The block's outer edges have no neighbour to borrow from, so those sides - and
only those - get `outer_bleed_mm`.

### The trim crop is the card; bleed is extra material outside it

**Reversed 2026-09-23.** The first implementation scaled each card's art to
*fill* its bled box (83 x 123 mm) and then cut at the trim line. Two things were
wrong with that, and the author caught both by looking at a real export:

1. The cut ate into the picture, so a printed card was a tighter crop than the
   grid tile - about 2.4% on each axis for a 928 x 1232 source.
2. Because bleed exists only on the block's outer edges, *which* 3 mm was lost
   depended on the slot: (0,0) lost its left and top, (1,1) its right and
   bottom. **The same card printed differently depending on where it landed.**
   That also made the preview structurally unable to be correct, since a card
   does not know its slot until export.

Now `crop_with_bleed` computes the **trim** crop first - exactly what
`crop_to_fill` returns and exactly what the thumbnail shows - and then takes
bleed from source pixels *outside* it, per side, clamped to what the source
actually has. The drawn box is the card box grown by the bleed that was
achieved, so the drawn box always equals the drawn image and a side that could
not bleed produces a smaller box rather than a white band.

`art_box` survives as the **nominal maximum**, which is what
`assert_placements_cover_cards` uses as an upper bound; the real invariant it
checks is that every placement *contains* its card box and stays inside that
maximum.

### Four-side bleed is impossible from source pixels alone

`crop_to_fill` is maximal: it keeps 100% of the width *or* 100% of the height.
So one axis never has a spare pixel, and bleed *taken from the source* on that
axis is always zero - for any source, at any resolution. Rendering art larger
does not change this.

That asymmetry is half of why sheet bleed was switched off (below); the other
half is that a card pushed to its focus limit has no spare pixels on that side
either, so it got no bleed while its neighbour got the full 3 mm.

**Narrowed 2026-09-23.** The sentence above is about *source* pixels, and the
press path escapes it: `crop_with_full_bleed` takes real pixels where they exist
and **mirrors the edge** to make up the shortfall, so all four sides are always
full. A press cuts on its own line with a mechanical tolerance and a short side
prints a white sliver, so "as much bleed as the source happened to have" is not
an option there the way it is on a sheet you cut yourself.

Mirroring rather than filling: whatever sits in the bleed is what shows on the
card edge if the cut drifts, so it has to continue the picture. A white band
would print as a sliver of exactly the thing bleed exists to prevent.

### Bleed is off: the drawn box is the cut box

**Reversed 2026-09-23, the author's decision.** `outer_bleed_mm` defaults to
**0**, so every drawn box is exactly its card box and nothing is printed outside
a cut line.

What it cost: a cut landing outside the block's outer perimeter now leaves a
hairline white sliver, where up to 3 mm of bleed would have covered it. The
author's call was to cut the outer border cleanly instead. Interior cuts are
unaffected either way - they are shared between two cards and compensate
themselves.

What it did **not** cost: any of the picture. The trim crop was already maximal,
so removing bleed shows exactly as much of a source as before - a 928 x 1232
upload framed 821 x 1232 px of itself with bleed on, and frames 821 x 1232 px
with it off. Bleed never zoomed anything in; that impression came from the older
bug above, where the trim line really was eating into the picture.

The machinery is kept, not deleted, and `export: bleed still works when switched
back on` keeps it proven: raise `outer_bleed_mm` and bleed returns, correctly,
on every side that has material to give. Crop marks moved in with it - they now
start 1.5 mm outside the block rather than 4.5 mm.

### One framing, three outputs

**Reversed within the same task, 2026-09-23.** The first implementation of the
press export cropped each source to the **bled** rectangle and let the trim line
cut inward from it. That is the textbook way to prepare press artwork, it is one
line shorter, and it was wrong here: adding equal bleed to a non-square changes
its aspect (80 × 120 mm is 0.667; the same card plus 3.048 mm a side is 0.683),
so the trim region showed a different slice of the source than the A4 sheet did.
Three outputs, three framings. The author caught it mid-task, before it shipped.

The rule now: **crop to the trim, then grow outward.** `crop_with_full_bleed`
returns an image whose trim region is byte-identical to `crop_to_fill` on the
same arguments — the same crop the grid tile shows and the same crop the PDF
draws — with the bleed added outside it.

This is the same ordering as the sheet path's "trim crop first, bleed second"
(above), and for the same reason. The difference is only what happens when the
source runs out of pixels: the sheet takes a short side, the press mirrors.

The gate asserts it for sources wider than the card, taller than it, and at
exactly its aspect, and **the assertion has been seen to fail** — planting the
rejected implementation turns it red while every other check stays green.

### Soft-art warnings live on the tile, not in the export

**Changed 2026-09-23, the author's call.** The export used to list every
soft-printing card twice: once in the dialog by name, and once in the finished
notification as a full sentence per card. On a real deck the second ran to
thousands of characters, pushed the Download button off the bottom of the
notification, and arrived after the work was already done.

Both are gone. What stays:

- the per-tile `soft` badge in the grid, and the editor's `· will print soft`,
  which is where the warning is *actionable* — before a batch is chosen, and
  pointing at the card you would have to replace;
- the count in the finished notification (`· 12 resolution warnings`);
- every warning string in the API response, for a caller that wants them.

The rule this is an instance of: a warning belongs where the reader can still
act on it. After the export it is not advice, it is noise.

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

### Image bytes live in the row, never a path

The sibling project `CardGenerator` learned this expensively: artwork addressed
by a path had two writers — an editable form field and the upload handler — and
pressing save after an upload restored the old path, silently discarding the
image just uploaded. Bytes have exactly one writer. The cost is a larger
database file; the benefit is that the file *is* the library.

The uploaded bytes are also never re-encoded. The crop happens at export time
from the original, so re-nudging a focus a hundred times costs nothing in
quality, and the gate asserts the library's pixels reach the PDF unresampled.

### Backs are their own table, not a flag on `cards`

A back has no tags and no notes, and must never appear in the overview you
batch-select from. A `kind` column would make that a filter every query has to
remember; a separate table makes it structural. The shared image columns come
from `ImageMixin`, so a column added to one is added to both.

### Hard delete — so `data/cards.db` is the file to back up

Deleting a card is permanent (the author's decision, 2026-09-22): the row and
its bytes go, and the database holds the only copy of the image. The
confirmation lives in the UI. Soft delete was offered and declined; recorded
here so the trade-off is visible rather than rediscovered.

### A thumbnail shows the print crop, not the source

Tiles are cropped to the card's aspect at the card's focus, so what you pick in
the grid is what the guillotine gives you. That makes the thumbnail a function
of the focus, which is why `set_focus` regenerates it.

### Dispose a connection pool before deleting its file

On Windows, SQLAlchemy's pooled SQLite connections keep the database file open,
and an open handle makes the file undeletable. The gate's `scratch_engine()`
calls `dispose()` before `unlink()`; without it every check after the first
died with `PermissionError: [WinError 32] The process cannot access the file
because it is being used by another process`.

### Turn CherryPy's trailing-slash redirect off

CherryPy answers `/api/export` with a 301 to `/api/export/`. A browser replays a
redirected POST as a **GET**, so every export from the UI arrived as
`GET /api/export/` and was refused 405 — while the identical call through `curl`
worked, because curl without `-L` does not follow it at all. `tools.trailing_slash.on`
is off for the whole app.

### Never pipe a server's stdout somewhere nobody reads

`check_gallery.py` starts its server with output going to a **file**. With
`stdout=subprocess.PIPE` and no reader, CherryPy's per-request logging fills the
OS pipe buffer (~64 KB on Windows) partway through the first page load — nine ES
modules, a stylesheet and several API calls — and the server then blocks forever
on its own log write. The symptom is maddening and points nowhere: the page
half-loads, the browser console is silent, and every selector times out.

### A browser check reports what the page looked like

When a check fails it prints the page's own status bar, the tile count, the
browser console and the tail of the server log, and saves a screenshot. The
client puts every API error into the status bar, so that one line usually *is*
the answer — without it the first two failures above cost far more than they
should have.

### `hidden` needs `!important` once, globally

The browser's `[hidden] { display: none }` lives in the UA stylesheet, so any
author rule that sets `display` beats it. `.editor { display: grid }` therefore
left a closed editor on screen as an empty bordered box, and `.dialog` needed
its own `[hidden]` rule to work around the same thing. One global
`[hidden] { display: none !important }` removes the class of bug rather than
patching each component.

The corollary for tests: Playwright's `wait_for_selector` defaults to
`state="visible"`, so waiting for `#panel[hidden]` waits for something that
cannot happen. Use `state="hidden"` — and note that the *broken* CSS made that
wait pass, because the element really was still visible.

### No rounded corners in the PDF

Dixit cards have rounded corners; a guillotine cuts square ones. A corner punch
after lamination is the intended finish. A printed radius that is then cut square
looks worse than no radius at all, so the export deliberately draws none.

### reportlab, not Pillow, for the PDF

Pillow can emit a multi-page PDF but gives no control over where on the page
anything lands, and cannot draw a vector crop mark. Exact millimetre placement is
the entire product here, so the heavier dependency is the right trade.
