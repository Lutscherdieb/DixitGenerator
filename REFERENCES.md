# DixitGenerator — external references & ground truths

**Every reference here is read-only: read freely, write never, at every entry point.** The `protect-references` hook blocks writes to declared paths; a deliberate exception is flipping `modules.references` off in `.claude/base-manifest.json` (visible, logged), never a quiet edit. If a task seems to require changing a reference, stop and warn the user.

This file is the single source of truth for references. The manifest's `readonly_refs` mirror is **generated from the entry frontmatter blocks below** — at scaffold time by `/base:new-project`, and re-derived by `/base:repo-setup` step 3 whenever references are (re)bound. Never hand-edit the mirror; `/base:doctor` check 10 and `/base:doc-audit` both check agreement. Machine-local paths live in gitignored `references.local.json` (`{"<id>": "<absolute local path>"}`) **at the repo root** — that exact location is where the hooks look, and a copy under `.claude/` is silently ignored, leaving every local reference unguarded. Bound per-machine by `/base:repo-setup`.

## Ground-truth routing

| Domain / question | Reference | Access method | Escalation when it runs out |
|---|---|---|---|
| How big is a Dixit card? What will a sleeve fit? | `dixit-card-spec` | `WebFetch https://www.sleeveyourgames.com/sleeves/643/dixit` | Measure a physical card with callipers and record the measurement, with the date and what was measured, as a blind-spot entry below. Retailers disagree by ~1 mm (see blind spots); a measurement beats a listing. |
| How many points is a millimetre? How big is A4 exactly? | `paper-and-pdf-units` | `WebFetch https://en.wikipedia.org/wiki/ISO_216`, `WebFetch https://developer.mozilla.org/en-US/docs/Web/CSS/length` | ISO 32000 (the PDF specification) for user-space units, ISO 216 itself for the paper series. Both are paywalled; the derived figures above are stable and asserted by the verify gate, so a paywall is not a blocker. |
| What does *my* printer actually do on a duplex pass? | none — this is measured, not referenced | `python tools/calibration_sheet.py`, then measure the printed sheet | Nothing. Printer drift is machine state, not a ground truth: it belongs in gitignored `printer.local.json`, never in git and never in a reference. |

## Registry

## Dixit card format

```yaml
id: dixit-card-spec
kind: website
readonly: true
local: false
committed_path: null
url: https://www.sleeveyourgames.com/sleeves/643/dixit
volatility: live
```

- **Access method:** `WebFetch https://www.sleeveyourgames.com/sleeves/643/dixit` for the card-size listing; `WebFetch https://www.maydaygames.com/products/dixit-card-sleeves` for the sleeve manufacturer's own figure. Both are retail listings, not a publisher spec — Libellud publishes no card dimension.
- **Comparison procedure:**
  1. Read the card dimension in millimetres from both sources above.
  2. Assert `CardFormat.DIXIT.trim_w_mm == 80` and `trim_h_mm == 120` — the sleeve standard, which is also the upper bound of every listed card figure.
  3. Cross-check the derivation on a format this project does **not** print: `mm_to_pt` applied to an MTG card (63 x 88 mm) must give 178.583 x 249.449 pt. A conversion checked only against the numbers it was built for cannot fail. `tests/run_tests.py` asserts exactly this.
- **Known blind spots / failed approaches:**
  - **The sources disagree by 1 mm on the width and it does not matter here.** MayDay lists the sleeve at 80 x 120 mm; one retailer describes the raw card as 79 x 120 mm (`"Dixit has 84 cards that are sized 79 x 120mm"`, retrieved 2026-09-22). We print 80 x 120 because a hand-cut, laminated card grows rather than shrinks, and 80 x 120 is what a sleeve is built for. Recorded so the next session does not "fix" 80 to 79.
  - **Libellud publishes nothing.** Every figure available is a sleeve manufacturer's or retailer's. Do not go looking for an official spec; it is not there. If precision ever matters more than it does now, measure a physical card and record the measurement here.

## Paper and PDF units

```yaml
id: paper-and-pdf-units
kind: website
readonly: true
local: false
committed_path: null
url: https://en.wikipedia.org/wiki/ISO_216
volatility: live
```

- **Access method:** `WebFetch https://en.wikipedia.org/wiki/ISO_216` for the A-series dimensions; `WebFetch https://developer.mozilla.org/en-US/docs/Web/CSS/length` for the point and inch definitions. ISO 216 and ISO 32000 themselves are paywalled standards; these are the accessible statements of the same figures.
- **Comparison procedure:**
  1. A4 is **210 x 297 mm** (ISO 216; the A-series has a √2 aspect ratio and A0 has an area of 1 m² before rounding to the nearest millimetre).
  2. **1 pt = 1 in / 72** and **1 in = 25.4 mm**, so `mm_to_pt(x) = x / 25.4 * 72`.
  3. Assert the derivation reproduces A4 in PDF user space: 595.276 x 841.890 pt. Any page box that is not that, to within 0.01 pt, is a failed export.
- **Known blind spots / failed approaches:**
  - **The CSS pixel is not the print pixel.** MDN defines `1in = 96px` because that is the CSS reference pixel. This project renders at **300 DPI**, so `1in = 300px` here. Never carry a `96` across from CSS documentation into the print path — read the `pt` and `mm` rows, ignore the `px` row.
  - **reportlab's default unit is the point, not the millimetre.** Every coordinate handed to it must already have gone through the spec module's conversion. A number that looks like a millimetre and is silently treated as a point is off by a factor of 2.835 and produces a plausible-looking, badly wrong sheet.

<!-- Section template (copy for a new reference):

## <Display name>

```yaml
id: <kebab-slug>
kind: website | api-spec | binary | upstream-repo | dataset | document
readonly: true
local: <true if the location is a machine-local path bound via references.local.json, else false>
committed_path: <repo-relative path if the reference lives inside this repo, else null>
url: <URL if the reference is remote, else null>
volatility: live | frozen-snapshot
```

- **Access method:** <the exact command/tool to read it, e.g. "WebFetch <url>", "Read <path>", a decompile procedure>
- **Comparison procedure:** <concrete steps to check our output against it>
- **Known blind spots / failed approaches:** <evidence-standard entries, or "none yet">
-->
