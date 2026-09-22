# DixitGenerator — learning log

Append-only harvest index. **The log is never a rule's home** — the rule itself is written into its owning doc/skill/hook (see CLAUDE.md's write-back task); each entry here just records that it happened, so `/base:promote` can find generic lessons and carry them to ClaudeBase. Every written-back lesson gets its entry **in the same edit** (the `check-lesson-tagging` hook nudges when one is missing its tags).

Entry statuses: `candidate` → `promoted-pr` (PR opened, add the URL) → `merged` | `rejected`. A `scope: generic` candidate with 2+ `applications:` dates is promotion-ready.

The entry shape (copy it, replacing every `<...>` — the angle brackets are what keep
this example from being scanned as a real candidate by `/base:promote`):

```
## <YYYY-MM-DD> — <short-imperative-slug>
- scope: <generic | project>
- status: <candidate>
- rule: <ONE imperative sentence — the rule as written into its home>
- home: <path#section where the rule now lives>
- evidence: <file:line / exact error text / N — the demoted story>
- applications: <date>[, <date>...]
```

## 2026-09-22 — seed-settings-enabledplugins-must-be-an-object
- scope: generic
- status: candidate
- rule: Write `.claude/settings.json`'s `enabledPlugins` as an OBJECT map (`{"base@claudebase": true}`), not a list. Base's seed template at 0.0.3 still emits the list form; after scaffolding, diff the generated settings file key-by-key against a file the host already accepts (`~/.claude/settings.json`) and confirm it parses before the first commit.
- home: .claude/settings.json (written in the object form at scaffold time), recorded as the `seed-settings-shape` divergence in .claude/base-manifest.json
- evidence: Claude Code reports the settings file as failing to parse even though the JSON is syntactically valid — the mismatch is schema, not syntax. `seed/.claude/settings.json.tmpl` in base 0.0.3 carries `"enabledPlugins": ["base@claudebase"]`; both the user's `~/.claude/settings.json` and the sibling CardGenerator repo use the object map. N=2 projects.
- applications: 2026-08-24, 2026-09-22

## 2026-09-22 — test-a-permutation-on-an-asymmetric-fixture
- scope: generic
- status: candidate
- rule: When testing a mapping that permutes positions, choose a fixture whose occupied positions are NOT symmetric under that permutation — otherwise the test passes for every possible mapping. State in the test why the fixture is shaped that way, so a later "simplification" does not restore the symmetric case.
- home: docs/ARCHITECTURE.md#the-flip-mapping-is-only-observable-on-a-part-full-sheet, tests/run_tests.py (`export: on a part-full sheet the back lands in the mirrored slot`)
- evidence: on a full 2x2 sheet the duplex-mirrored slots occupy exactly the same four art boxes as the fronts, so a four-card fixture cannot distinguish long-edge from short-edge from no flip at all. A one-card fixture makes the difference visible: long-edge puts the back in slot (0,1), short-edge in (1,0).
- applications: 2026-09-22

## 2026-09-22 — compare-derived-integers-not-recomputed-floats
- scope: generic
- status: candidate
- rule: When a threshold is stated to the user in derived units ("at least 945 x 1417 px"), compare against that derived integer, not against a float recomputed from it. Add a boundary case at exactly the stated value to the test suite in the same edit.
- home: src/dixitgen/spec/card.py (`CardFormat.art_is_soft`), docs/ARCHITECTURE.md#compare-pixel-counts-not-computed-dpi-for-the-soft-art-warning, tests/run_tests.py (`units: art at exactly the derived pixel size is not called soft`)
- evidence: `effective_dpi(1417, 120) == 299.93` because 1417 is `round(120/25.4*300)`, so a `< 300` test called art of exactly the advertised size "soft". Caught only because the boundary case 945x1417 was tried; 1024x1024 and 2048x3072 both behaved correctly and would have shipped the bug.
- applications: 2026-09-22

## 2026-09-22 — a-literal-checker-must-read-code-not-comments
- scope: generic
- status: candidate
- rule: A checker that greps source for forbidden literals must strip comments and docstrings first, then prove both directions: plant the literal in a code line (must fail) and in a comment (must pass). A checker that flags the prose explaining its own rule trains people to ignore it.
- home: tools/check_geometry_literals.py (`code_lines`), docs/ARCHITECTURE.md#a-measurement-in-a-comment-is-prose-not-a-source-of-truth
- evidence: the first working version reported 4 findings, all inside `check_geometry_literals.py`'s own docstring, which uses `80mm`, `945px`, `226.77pt` and `595.276pt` as examples of what it looks for. Both directions are now exercised: a planted `const CARD_W = "80mm"` exits 1, the same text in a `//` comment exits 0.
- applications: 2026-09-22

## 2026-09-22 — a-reused-resource-is-stored-once-in-the-artefact
- scope: project
- status: candidate
- rule: When checking a generated artefact, never assume one stored resource per placement. Pair a placement with its resource by the NAME the placement carries (`embedded_images_by_name`), not by index or count.
- home: tests/pdf_probe.py (`embedded_images_by_name`), docs/ARCHITECTURE.md#a-repeated-image-is-one-xobject-not-one-per-placement
- evidence: a back page draws the same back image into four slots; the PDF stores one XObject referenced four times. `equal(len(images), len(page.placements))` failed with `page 1: embedded rasters vs placements: got 1, expected 4` — the test was wrong, not the export.
- applications: 2026-09-22
