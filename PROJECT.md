# DixitGenerator — constitution

## Goal

Turn uploaded artwork into print-ready A4 duplex PDF sheets of 80 x 120 mm Dixit-format cards, with an overview to organise and batch-select them.

A local tool for making custom Dixit cards. Images go in; a browser overview keeps them organised by name, tags and notes; any selection exports as A4 sheets at 300 DPI — fronts 2x2 with crop marks in the paper margin, plus matching back sheets using one chosen back image, laid out so front and back register when printed double-sided on a home printer. The card **is** the image: nothing else ever prints on it.

The print geometry is the product. Everything else in the repo exists to serve it.

## Non-goals

- **Not a print-service uploader.** No MakePlayingCards / PrinterStudio upload specs, no press bleed. Output targets a home printer, a guillotine and a laminator. (The sibling project `CardGenerator` covers the MPC path; do not import its `Profile` model — its numbers are press numbers.)
- **Not internet-facing.** The overview binds to localhost for a single user. No accounts, no sharing, no hosting. Anything assuming multiple users or a public URL is out of scope until that decision is explicitly revisited.
- **Not an art tool.** Artwork is authored elsewhere and uploaded; the tool crops, places and warns when an image is too small to print sharply.
- **Not a card designer.** No name, text, symbol, frame, border or number may ever print on a card. This is the product's defining constraint, not a missing feature — a request to add one is a request to build a different tool.
- **Not a Dixit rules implementation.** Nothing here knows or executes how the game is played.

## Users

Just me, on this machine.

## Quality bars & definition of done

- A change is done when: it's implemented, its mapped docs are current (see the documentation contract below), and the verify method below has actually been run with its output checked.
- **A misregistered back is a failed export, not a warning.** The front/back slot mapping is asserted inside the export pipeline, so a PDF whose backs do not line up with its fronts never reaches the output directory. Do not downgrade an assertion to a log line.
- **Nothing may print inside a card box but that card's image.** Crop marks, page furniture and debug overlays live in the paper margin; the export asserts no drawn element intersects a card box.
- **Preview before writing** any new design, schema change, or data migration — show what will change and get an explicit OK first.
- Escalate when simple turns complex: if a change starts touching the geometry, the store and the export at once, stop and say so before continuing.
- **A task is not done while a server Claude started is still listening.** The overview on 8775 is the author's, started from `serve.bat`; Claude may run its own throwaway on 8776 for testing, and closing it is part of the close-out — see the server rule in [CLAUDE.md](CLAUDE.md).

## Verify method

Export a fixture batch in all three duplex modes, then **parse the produced PDFs back** and assert the geometry against the spec module. This covers the one thing the product promises — that a printed, cut card is 80 x 120 mm and its back lines up — so a drifted measurement or a broken flip mapping fails loudly instead of being discovered on paper.

The gate asserts, per export:
- the page box is exactly A4 (595.276 x 841.890 pt);
- there are exactly four card boxes per front page, at the exact expected mm positions;
- every card box is exactly 80 x 120 mm;
- each back slot registers with its front slot under the batch's chosen flip;
- no crop mark or other drawn element intersects a card box;
- every embedded raster resolves to at least 300 DPI at its placed size.

Plus the derivation cross-check: the mm-to-point conversion must reproduce figures this project never hardcodes — A4 at 595.276 x 841.890 pt, and an MTG card (63 x 88 mm) at 178.583 x 249.449 pt. A conversion checked only against the numbers it was built for is unfalsifiable.

- Command: `python tests/run_tests.py > tests/last-run.txt 2>&1`
- Evidence: `tests/last-run.txt`
- Exempt: `["**/*.md", "data/**", "out/**"]`

Run it from VS Code with **Terminal -> Run Task -> `Verify`**, or by hand with the command above.

**The gate does not cover the browser overview.** `web/**` is mapped to `docs/ARCHITECTURE.md` but deliberately kept out of `source_globs`: exporting a PDF proves nothing about the browser UI, so demanding the gate for a frontend edit would be ritual rather than verification. The frontend's check is `tests/check_gallery.py`, which drives real Chromium through upload, selection, the crop drag, filtering, the backs shelf, export and delete. Run it with no arguments and it starts its own throwaway server on 8776 against a scratch database and stops it again. Set `DIXIT_URL` to point it at a server you started yourself — and note that it **writes**, so it refuses to run against the real library (`/api/meta` reports `is_default_library` for exactly this).

Uploaded artwork is validated separately and advisorily: an image that resolves below 945 x 1417 px at the card's placed size gets a soft-print warning. That is a warning by design, never a block — a deliberately low-res or painterly source is the author's call.

## Documentation contract

| Document | What it promises its reader |
|---|---|
| `README.md` | What this is, current status, how to run + verify it |
| `docs/ARCHITECTURE.md` | How an upload becomes a PDF: where the geometry comes from, how a batch is composed, and which module owns what |
| `docs/PRINTING.md` | How to actually print, calibrate and cut: duplex settings, the calibration procedure, paper, blade and lamination notes |

## References summary

- **Dixit card format** — the published physical card and sleeve dimensions (80 x 120 mm) that `CardFormat` must satisfy. Live website.
- **Paper and PDF units** — ISO 216's A4 figure in millimetres and the PDF/PostScript user-space unit (1/72 in), which every millimetre-to-point conversion is checked against. Live website.

## Open direction notes

- **Built: the print geometry, the crop, the card library, the API, the browser overview and the export.** The one piece left from the original plan is `tools/calibration_sheet.py`.
- **No bleed: the printed area is the card, edge to edge.** Decided 2026-09-23 after the author saw a real export. Bleed existed only on the block's outer edges and only where a source had spare pixels, so a card pushed to its focus limit got none while its neighbour got 3 mm — not worth the asymmetry. The outer border is cut cleanly instead; interior cuts are shared and self-compensating. The machinery is kept and still tested, so raising `SheetLayout.outer_bleed_mm` brings it back.
- **`data/cards.db` holds the only copy of every uploaded image, and deletion is permanent.** That was the deliberate choice over soft delete (2026-09-22): the confirmation lives in the UI. Back the file up before a big tidy-up — it is one file, and copying it copies the whole library.
- **The calibration sheet is not optional polish.** Home-printer duplex drift of 1-2 mm is normal and is exactly the error that ruins a batch of 84 cards. Build `tools/calibration_sheet.py` before the first real print run, not after.
- **Decide how a batch remembers its back.** An export currently takes a back image as a parameter. If re-exporting the same deck becomes routine, a saved batch (selection + back + duplex mode) is worth more than a bigger export dialog. Author's call once the overview exists.
- **Corner rounding is a manual step.** Dixit cards have rounded corners; a guillotine cuts square ones. A corner punch after lamination is the intended finish — the PDF deliberately draws no corner radius, because a printed radius you then cut square looks worse than no radius at all.
