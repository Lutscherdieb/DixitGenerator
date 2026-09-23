# DixitGenerator — project rules

Turn uploaded artwork into print-ready A4 duplex PDF sheets of 80 x 120 mm Dixit-format cards, with an overview to organise and batch-select them.

<!-- BASE:doctrine-header:v1 START -->
This repo was created from **ClaudeBase** (the version at creation, and the last synced one, are recorded in `.claude/base-manifest.json`). The generic machinery — setup, audits, sync, harvest — arrives via the `base` plugin and updates with it; this file and the other seeded docs are owned by this project, except the `BASE:` marker regions, which `/base:sync` maintains (never hand-edit inside them — needing to is a missing-interview-question bug in Base, file it as a lesson). `/base:doctor` shows status. No personal data in version control: no real names, emails, machine-specific absolute paths, or session IDs — machine-local state lives in gitignored `*.local.*` files.
<!-- BASE:END -->

## What this project is

See [PROJECT.md](PROJECT.md) — the constitution: goal, non-goals, quality bars, verify method, and the documentation contract. Generic skills read it first; keep it current when direction changes.

## The hard rule: external references are read-only

This project's declared ground truths are registered in [REFERENCES.md](REFERENCES.md).

<!-- BASE:doctrine-references:v1 START -->
**Read freely, write never — at every entry point.** Each reference's access method and comparison procedure live in REFERENCES.md; the `protect-references` hook blocks writes to declared paths. If a task seems to require editing a reference, **stop and warn the user instead of proceeding**, even if only part of a larger task touches it. A deliberate exception is made by flipping `modules.references` off in `.claude/base-manifest.json` — a visible, logged act — never by quiet edits.
<!-- BASE:END -->

<!-- BASE:doctrine-writeback:v1 START -->
## The highest-priority standing task: turn every lesson into a *rule*, not a war story

**Improving this project's workflow, skills, and docs with what a task teaches is the single most important recurring job — above finishing any individual feature.** A lesson only counts once it's written as a **prescriptive rule that tells the next session what to DO**, not a "gotcha" describing what went wrong. The test: *could someone follow this without already knowing the story behind it?*

When writing a finding back:
1. **Lead with the imperative** — a step someone executes.
2. **Include the verification step** if the failure was "I thought I had done it right" — an instruction that can be silently satisfied wrongly needs a check that proves it was satisfied.
3. **Keep the evidence, demote it** — `file:line`, exact error text, sample size N — *after* the rule, never in place of it. Record failed approaches too; they're the expensive knowledge to rediscover.
4. **Prefer removing the choice over documenting the hazard** — a helper that can't be called wrongly beats any warning text.

The escalation ladder for a recurring failure: prose warning → imperative rule + verification step → audit detection recipe → hook. A rule that gets violated *after* being written down is evidence the writing was in the wrong **form**, not that people need reminding.

**Every written-back lesson also gets a `.claude/learning-log.md` entry in the same edit**, tagged `scope: generic|project` with an `applications:` date list (the log is the harvest index, never the rule's home). A `generic` lesson applied 2+ times is a `/base:promote` candidate — that's how improvements discovered here reach ClaudeBase and every sibling project. Needing to hand-edit a Base-owned file or `BASE:` region is itself always a `generic` lesson ("Base is missing an option/question").
<!-- BASE:END -->

<!-- BASE:doctrine-docs:v2 START -->
## Documentation is the user interface of this project

The user reads this project's state through the docs named in PROJECT.md's documentation contract. **A change to a mapped source area isn't done until its mapped doc is current** — same weight as the verify gate; the `check-doc-freshness` hook nudges on the manifest's `doc_map`. Rules:
- `AUTO:` regions in docs are generated — never hand-edit inside them; content that must survive regeneration sits outside the markers.
- Root README and contract docs are **not** create-late: they exist from day one and stay current without asking. Optional deep-dive docs are create-late-ask-first; but once one exists, keep it current, don't ask again.
- A new skill/doc file, or a structural edit to one, isn't done until a scoped `/base:doc-audit` cold-test covers the changed files (wording-only fixes exempt). One convention, one home: an index/checklist row links to the owning doc, never restates it.
- Authoring or restructuring a project skill follows `/base:skill-author` (two-tier SKILL.md + `references/` split by content shape, reference-index table, description-line triggers, no confusable names next to `/base:*` skills).
- Documented reversals stay in place, marked as reversed with the reason — a retired idea that vanishes gets re-derived.
- Derive, don't enumerate: no doc or hook hardcodes a list (of modules, files, features) that the manifest or the tree can supply.
<!-- BASE:END -->

<!-- BASE:doctrine-verify:v1 START -->
## Nothing is "done" untested

Every change inside the manifest's `source_globs` ends with the verify method from PROJECT.md actually run and its output checked before being reported as done — silent breakage is common and doesn't always error loudly. Proportionality: changes matching `verify.exempt_patterns` (pure docs/wording) skip this, but a mixed edit that also touches source doesn't. Evidence standard for any claim written back: `file:line`, the exact error text (the next person greps for that string), and sample size N when the conclusion rests on frequency.
<!-- BASE:END -->

## Project-specific rules

### Never hardcode a print measurement — ask `dixitgen.spec`

Every measurement (page, card, grid, margin, bleed, crop-mark length, DPI, a point value, a pixel value) comes from `CardFormat` or `SheetLayout` in `src/dixitgen/spec/`. Python asks the object directly; anything that needs a number in another language receives it through a generated value, never by being typed a second time.

**Verification step:** after any change touching geometry, layout or export, run `python tools/check_geometry_literals.py`; it must exit 0. It asks the spec module for the number list and greps for each one **unit-anchored** (`80mm`, `226.77`, not a bare `80`), so a measurement added to `CardFormat` or `SheetLayout` is covered the day it exists. Do not replace it with a hand-written grep over specific numbers: that form can only catch drift somebody already thought of.

**It derives the *objects* too, not just their fields** — it loops over `CARD_FORMATS` and `PRESS_FORMATS`, so registering a format covers its measurements on the same commit. **When you add a format, prove that**: plant one of its new numbers unit-anchored in a `web/` or `src/` file and confirm the checker exits 1 and names the owning object, then remove it. A "clean" from a checker that never looked is the failure mode this tool exists to prevent.

*Evidence (inherited, `CardGenerator` 2026-08-24 and 2026-08-31):* in the sibling project the card canvas size existed in four disagreeing copies across Python, CSS and an SVG template, and all four were wrong against the published spec. A later hand-written grep stayed green while `--road-width: 214px` sat in a stylesheet as a second source of truth, because `214` was not in the list somebody had thought to write. This project starts with the derived form to avoid re-earning both lessons.

### Take the card and paper figures from the published spec, never from a code comment

Before changing any print measurement, WebFetch the reference registered in [REFERENCES.md](REFERENCES.md) and follow its comparison procedure.

**Verification step:** the derivation must reproduce a published figure for a case we do **not** print — A4 at 595.276 x 841.890 pt, and an MTG card (63 x 88 mm) at 178.583 x 249.449 pt. `tests/run_tests.py` asserts exactly this; a conversion that fails it is wrong even if the Dixit numbers happen to look right.

*Evidence:* `1 pt = 1 in / 72` and `1 in = 25.4 mm` (MDN, retrieved 2026-09-22); A4 = 210 x 297 mm (ISO 216, retrieved 2026-09-22). MDN's `1in = 96px` is the CSS reference pixel and is **not** this project's pixel — see the blind spot recorded on the reference.

### Front/back registration is an assertion, not a hope

An exported batch asserts, before any PDF is written, that every back slot maps to its front slot under the batch's chosen flip: long-edge mirrors the grid horizontally (`col -> cols-1-col`); short-edge mirrors it vertically (`row -> rows-1-row`) **and** rotates the back image 180°, so a cut card flipped left-to-right shows its back upright; manual two-file output defaults to the long-edge mapping. A mismatch raises, it does not warn.

**Verification step:** `python tests/run_tests.py` exports in all three modes and parses the PDFs back to check the mapping. Never assert the mapping only against the in-memory layout object — that checks that the code agrees with itself. Read it out of the written file.

### Nothing prints inside a card box but that card's image

No text, border, frame, registration mark, page number or debug overlay may intersect a card box. Crop marks live in the paper margin, outside the 2x2 block. The export asserts this over every drawn element, and the assertion is the enforcement — a review by eye does not count, because a 0.2 mm intrusion is invisible on screen and visible on a laminated card.

### The overview server: `serve.bat` starts it, 8775 is yours, 8776 is Claude's

The overview you browse is **user-owned** and long-lived. Its one launcher is `serve.bat` at the repo root, run in the VS Code terminal panel: **Terminal -> Run Task -> `Overview: serve`** (the default build task, so `Ctrl+Shift+B` runs it too). It stays in the foreground, so `Ctrl+C` in that panel stops it. It listens on **8775**.

The ports are deliberately not `CardGenerator`'s 8765/8766: both tools are galleries over a SQLite database on the same machine, and the whole point of a separate stop command is that it cannot reach the wrong server.

1. **Probe 8775 first. If something answers, it is the user's — use it, never stop it.** Point the checks at it; `tests/check_gallery.py` honours `DIXIT_URL`, so reusing a running server is the normal path, not a workaround.
2. **A server Claude starts goes on 8776, and is stopped in the same turn.** `serve.bat 8776`, checks run with `DIXIT_URL=http://127.0.0.1:8776`, `stop-server.bat 8776` before reporting done.

**Call a `.bat` from a Bash-style shell as `cmd //c "<absolute path to the .bat>" <args>`.** The two shorter forms both fail *without failing*: `cmd //c stop-server.bat 8776` reports "is not recognized" (the `//c` rewrite drops the working directory), and `cmd.exe /c "stop-server.bat 8776"` opens an interactive `cmd` and exits, printing the Windows banner and a prompt instead of running anything. Neither returns a non-zero exit code, so a stop that silently did nothing looks exactly like a stop that worked.

**Verification step:** probe before assuming, and account for the port after. Up: `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:<port>/api/meta` returns `200`. Before reporting a turn done that started a server: `netstat -ano | findstr LISTENING | findstr :877` must show nothing beyond the listeners that were already there when the turn began — check the listener lines, not the whole `netstat` output, which is full of `TIME_WAIT` rows that mean the opposite.

*Evidence (inherited, `CardGenerator` 2026-08-24):* a gallery started as a background process on the default port had no window to interrupt and had to be killed through Task Manager.

### Printer calibration is machine-local state, never committed

A home printer's duplex front/back drift is a property of one machine and one paper path. It lives in gitignored `printer.local.json` at the repo root, written by `tools/calibration_sheet.py`'s measurement step and applied to back pages only.

**Verification step:** `git check-ignore -v printer.local.json` must name a `.gitignore` rule. A calibration offset that reaches git silently mis-registers someone else's printer — and on this project's own terms, a machine-specific number in version control is a doctrine violation regardless of whether it happens to be harmful.

### A committed generated file prints repo-relative paths, never absolute ones

`tests/last-run.txt` is committed verify evidence, so every path it prints is in version control. Any generator whose output is committed — the verify gate, a report, a manifest — formats paths as `p.relative_to(ROOT).as_posix()`, so the text is byte-identical on every machine and carries nobody's directory layout. The repo is public; a path like `<drive>:\<repo>\out\verify` published a user's drive and folder tree.

**Verification step:** before any push, this must exit 1 (no match):

```
git grep -nIE '[A-Za-z]:[\][^\]*[\]|[A-Za-z]:/[A-Za-z0-9_. -]+/|/(home|Users)/[A-Za-z0-9_.-]+/' -- .
```

Write the backslashes as bracket expressions `[\]`, not as `\\`. **A `git grep -E` pattern whose alternative ends in `\\|` silently degrades** — git reads the escaped pipe as a literal `|`, the alternation collapses into one branch, and the check reports clean while matching nothing. It exits 1, indistinguishable from a real pass. Keep every example path in this file redacted (`<drive>:\<repo>\...`) so the check never flags the prose that explains it. Prove the pattern on a planted fixture (a file containing an absolute path, staged in a throwaway repo, must be reported) before trusting an exit 1 from it.

*Evidence (2026-09-23, setting up the GitHub remote):* `tests/last-run.txt:5` carried `output : <drive>:\<repo>\out\verify` into what became a public repo. The first pattern written to find it used `\\` and returned exit 1 on a repo that did contain the path; `git grep` reported `fatal: ... 'Trailing backslash'` only once the alternation was removed. Note also that `printf '<drive>:\<repo>\out\verify'` mangles its own fixture (`\v` becomes a vertical tab) — build path fixtures with a quoted heredoc.

### One crop serves every output — add bleed outside the framing, never crop to it

A card is framed **once**, by its trim rectangle: `crop_to_fill(img, card.trim_w_mm, card.trim_h_mm, focus)`. The A4 sheet, the plain image export and the press files all show that crop. A press's bleed is added **outside** it by `crop_with_full_bleed`, which takes real source pixels where they exist and mirrors the edge for the shortfall.

**Never crop a source to a bled rectangle.** Adding equal bleed to a non-square changes its aspect (80 x 120 mm is 0.667; the same card plus 3.048 mm a side is 0.683), so the trim region then shows a different slice of the source than the sheet does — the same card, framed differently in each output.

**Verification step:** `python tests/run_tests.py` asserts that a press file's trim region is byte-identical to `crop_to_fill` on the same source, for a source wider than the card, one taller than it, and one at exactly its aspect. Do not weaken it to a size comparison: the bled-rectangle bug produces an image of a plausible size and wrong content. Prove the assertion still bites after touching the crop path — replace `crop_with_full_bleed` with `crop_to_fill(img, press.bled_w_mm, press.bled_h_mm, focus)` and the check must go red while every other check stays green.

*Evidence (2026-09-23):* the first implementation of the MPC export did crop to the bled rectangle — the textbook way to prepare press artwork, and one line shorter. It passed every other check in the gate. The author caught it by reading the design, not the output, and said so mid-task: *"we want the exported images and the exported pdf images be the same cropped image size so we don't have the images deviating"*.

### A warning belongs where the reader can still act on it

Soft-resolution warnings appear on the grid tile and in the editor — per card, before a batch is chosen, pointing at the image you would have to replace. **The export flow shows no warning text**: not in the dialog, not in the finished notification. The finished notification keeps the count only, and the API still returns every warning string.

Do not "helpfully" re-add a list of affected cards to an export result. After the export the work is done; a wall of text there is not advice, it is something to scroll past to reach the Download button.

*Evidence (2026-09-23, the author's request):* the finished notification joined one full sentence per soft card with `·`. On a real deck that ran to thousands of characters and pushed the Download action off the bottom of the notification.
