# DixitGenerator

Turn uploaded artwork into print-ready A4 duplex PDF sheets of 80 x 120 mm Dixit-format cards, with an overview to organise and batch-select them.

## Status

**Usable end to end.** Drop images in, organise them, select a batch, export
print-ready A4 sheets — or the same cards as per-card image files.

Two checks, both green:

- `python tests/run_tests.py` — the verify gate, **42 checks**. Exports fixture
  batches in all three duplex modes and parses the PDFs back off disk to measure
  them; checks that a cut card shows exactly the grid tile's crop in every slot,
  and that a press file shows that same crop with its bleed outside it; and
  exercises the library from upload through crop focus, tags and delete to the
  raster embedded in the PDF.
- `python tests/check_gallery.py` — **18 checks** driving real Chromium: upload,
  select, drag the crop on a card and on a back, filter, both export kinds with
  their progress notifications, and delete. It starts
  its own throwaway server on 8776 with a scratch database and stops it again,
  and refuses to run against your real library.

Not built yet: `tools/calibration_sheet.py`. Until it exists, the calibration
procedure in [docs/PRINTING.md](docs/PRINTING.md) works today — print a test
sheet, hold it to the light, and read the gap between the front and back crop
marks.

## What this is

A local tool for making custom Dixit cards. Images go in; a browser overview keeps them organised by name, tags and notes; any selection exports as A4 sheets at 300 DPI — fronts 2×2 with crop marks in the paper margin, plus matching back sheets using one chosen back image, laid out so front and back register when printed double-sided on a home printer.

The card **is** the image. No name, text, symbol, frame or border ever prints on one — that is the product's defining constraint, not a missing feature.

Any selection can also be written as **per-card PNG files in a zip** instead of sheets:

| Output | What you get |
|---|---|
| **A4 duplex sheets (PDF)** | The default. 2×2 per sheet, crop marks in the margin, backs registered for duplex |
| **MakePlayingCards ready** | One 1017 × 1489 px PNG per card — the card plus 36 px of that press's bleed a side — and one shared `back.png` |
| **Cropped images only** | The trim crop each tile shows, at the source's own resolution. Nothing is resampled |

**All three show the same crop.** A card is framed once and press bleed is added outside that framing, so a card ordered from a press and a card cut off an A4 sheet are the same picture. The verify gate asserts it.

One caveat worth knowing before you order: MakePlayingCards publishes **no 80 × 120 mm card**. Their nearest is a tarot card at 69.85 × 120.65 mm — 10 mm narrower. This project exports its own size and leaves matching Dixit cards intact, which means ordering goes through MPC's custom-size path and may be declined. If it is, [PROJECT.md](PROJECT.md) records the fallback: move every output to tarot together, which is a one-line change and is already exercised by the gate.

Output otherwise targets a home printer, a guillotine and a laminator. The sibling project `CardGenerator` still covers its own service's path; its numbers are its own and do not belong here.

## Run & verify

```
pip install -e .
```

Then **Terminal → Run Task → `Overview: serve`** (the default build task, so `Ctrl+Shift+B` runs it too), or `serve.bat` from the repo root. It stays in the foreground; `Ctrl+C` stops it.

    Overview:  http://127.0.0.1:8775/web/index.html

Port **8775 is yours**. A throwaway server for testing belongs on **8776** and is stopped in the same turn — see [CLAUDE.md](CLAUDE.md). `stop-server.bat [port]` kills a server that has no window to interrupt.

Verify a change with: `python tests/run_tests.py > tests/last-run.txt 2>&1`

## Layout

| Path | What it is |
|---|---|
| [`src/dixitgen/spec/`](src/dixitgen/spec/) | **The only source of print measurements.** Units, card format, sheet layout, and the geometry assertions everything else is held to |
| [`src/dixitgen/render/`](src/dixitgen/render/) | Crop-to-fill and grid thumbnails: how an upload of any shape becomes a card-shaped image |
| [`src/dixitgen/store/`](src/dixitgen/store/) | The card library. **`data/cards.db` holds the image bytes, so it is the whole library — and the file to back up** |
| [`src/dixitgen/export/`](src/dixitgen/export/) | Batch → A4 PDF sheets, or per-card PNGs in a zip. The only writer of print output |
| [`src/dixitgen/web/`](src/dixitgen/web/) | The local JSON API (CherryPy). `/api/meta` serves the spec to the browser |
| [`src/dixitgen/cli.py`](src/dixitgen/cli.py) | `dixitgen serve` — what `serve.bat` calls |
| [`web/`](web/) | The browser overview: static ES modules, no build step, acyclic. Types no measurement of its own — they all arrive from `/api/meta` |
| [`tests/`](tests/) | `run_tests.py` (the verify gate), `pdf_probe.py` (reads a written PDF back into millimetres), and `check_gallery.py` (drives a real browser) |
| [`tools/`](tools/) | `check_geometry_literals.py`: fails if a measurement is typed outside `dixitgen.spec` |
| `data/` | SQLite database (gitignored) |
| `out/` | Exported PDFs and image archives (gitignored) |
| [`docs/`](docs/) | [ARCHITECTURE.md](docs/ARCHITECTURE.md) (how it fits together) and [PRINTING.md](docs/PRINTING.md) (how to print and cut) |

More: [PROJECT.md](PROJECT.md) (goals, quality bars, doc contract) · [REFERENCES.md](REFERENCES.md) (declared ground truths).

<!-- BASE:readme-footer:v1 START -->
---
<sub>Built on [ClaudeBase](https://github.com/Lutscherdieb/ClaudeBase): the workflow machinery (setup, audits, doc gates, sync/harvest loop) arrives via the `base` Claude Code plugin and updates with it.</sub>
<!-- BASE:END -->
