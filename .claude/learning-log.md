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
- rule: Before asserting that an input changes an output, check the fixture actually has the degree of freedom being tested — a fixture symmetric under the mapping, or already at the target shape, passes for every possible implementation. State in the test why the fixture is shaped that way, so a later "simplification" does not restore the degenerate case.
- home: docs/ARCHITECTURE.md#the-flip-mapping-is-only-observable-on-a-part-full-sheet, tests/run_tests.py (`export: on a part-full sheet the back lands in the mirrored slot`)
- evidence: TWICE on 2026-09-22. (1) On a full 2x2 sheet the duplex-mirrored slots occupy exactly the same four art boxes as the fronts, so a four-card fixture cannot distinguish long-edge from short-edge from no flip at all; a one-card fixture makes it visible (long-edge -> slot (0,1), short-edge -> (1,0)). (2) The "changing the focus regenerates the thumbnail" check used a 1200x1800 fixture, which is already the card's 2:3 aspect, so `crop_to_fill` has zero crop freedom and no focus can move the window — the test failed against correct code with `the thumbnail bytes are unchanged`. A square fixture gives the horizontal freedom the check needs; the degenerate case is now asserted separately as correct behaviour.
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
- applications: 2026-09-22, 2026-09-23

## 2026-09-22 — a-reused-resource-is-stored-once-in-the-artefact
- scope: project
- status: candidate
- rule: When checking a generated artefact, never assume one stored resource per placement. Pair a placement with its resource by the NAME the placement carries (`embedded_images_by_name`), not by index or count.
- home: tests/pdf_probe.py (`embedded_images_by_name`), docs/ARCHITECTURE.md#a-repeated-image-is-one-xobject-not-one-per-placement
- evidence: a back page draws the same back image into four slots; the PDF stores one XObject referenced four times. `equal(len(images), len(page.placements))` failed with `page 1: embedded rasters vs placements: got 1, expected 4` — the test was wrong, not the export.
- applications: 2026-09-22

## 2026-09-22 — dispose-a-connection-pool-before-deleting-its-file
- scope: generic
- status: candidate
- rule: On Windows, call `engine.dispose()` before unlinking a SQLite file a test created. A pooled connection holds an open handle and the delete fails; a test that recreates its scratch database per case must dispose the previous engine first.
- home: tests/run_tests.py (`scratch_engine`), docs/ARCHITECTURE.md#dispose-a-connection-pool-before-deleting-its-file
- evidence: `PermissionError: [WinError 32] The process cannot access the file because it is being used by another process: 'out\verify\scratch-library.db'` — 8 of 9 store checks failed this way; the first passed because nothing was holding the file yet. POSIX would have allowed the unlink silently, so this is a Windows-only trap that CI on Linux would not catch.
- applications: 2026-09-22

## 2026-09-22 — sample-a-fixture-away-from-its-own-boundaries
- scope: generic
- status: candidate
- rule: When asserting on pixels, take the sample well inside a region of uniform value — never where two regions meet. Choose the fixture so the sample points and the region boundaries cannot coincide after the transform under test, and say so in the fixture's docstring.
- home: tests/run_tests.py (`band_fixture` docstring)
- evidence: `corner_colour` samples at 1/4 and 3/4 of each axis. Cropping a square quadrant fixture to 2:3 keeps two thirds of the width, putting the 3/4 sample exactly on the red/green seam: the assertion read `RGB(108, 146, 2)` and failed against correct code. Three vertical bands at thirds put every sample point in the middle of one colour.
- applications: 2026-09-22

## 2026-09-22 — never-pipe-a-subprocess-log-nobody-reads
- scope: generic
- status: candidate
- rule: When a test starts a long-running server as a subprocess, send its stdout/stderr to a FILE, never to `subprocess.PIPE` that nothing drains. Print the file's tail when a check fails, so the server's own account of the request is in the failure output.
- home: tests/check_gallery.py (`start_server`, `_server_log_tail`), docs/ARCHITECTURE.md#never-pipe-a-servers-stdout-somewhere-nobody-reads
- evidence: CherryPy logs one line per request. With `stdout=subprocess.PIPE` unread, the OS pipe buffer (~64KB on Windows) filled partway through the first page load — nine ES modules, a stylesheet and several API calls — and the server blocked forever writing its own log. The symptom points nowhere: the page half-loads, the browser console is silent, and every selector times out. The same page loaded fine by hand because the log went to a file.
- applications: 2026-09-22

## 2026-09-22 — wait-for-a-readiness-signal-not-a-static-element
- scope: generic
- status: candidate
- rule: Have the app set an explicit readiness flag (`document.body.dataset.ready`) when its first load completes, and have browser checks wait on that. Never wait on an element that exists in the served HTML — it is present before any data arrives, so the check races the app and passes or fails by luck.
- home: web/app.js (end of `main`), tests/check_gallery.py (`run_checks` first wait), docs/ARCHITECTURE.md#dixitgenweb--web--the-overview
- evidence: the check waited for `#spec-line`, which is in index.html carrying the placeholder "Loading the print spec…". It passed on one run and failed the next with `the header does not show the card format from /api/meta: 'Loading the print spec…'` — same code, different timing.
- applications: 2026-09-22

## 2026-09-22 — a-redirect-turns-a-post-into-a-get
- scope: generic
- status: candidate
- rule: Make the server answer the exact URL the client calls; do not let a framework's trailing-slash redirect stand in front of a POST endpoint. A browser replays a redirected POST as a GET, so the handler sees the wrong method and the body is gone. Verify with a browser, not curl: curl without `-L` does not follow the redirect at all and reports success.
- home: src/dixitgen/web/app.py (`tools.trailing_slash.on: False`), docs/ARCHITECTURE.md#turn-cherrypys-trailing-slash-redirect-off
- evidence: `POST /api/export HTTP/1.1" 301` followed immediately by `GET /api/export/ HTTP/1.1" 405` in the server log. Export was broken from the UI and working through curl; only tests/check_gallery.py, driving a real browser, could see it. This is the concrete payoff for keeping a browser check separate from the verify gate.
- applications: 2026-09-22

## 2026-09-23 — define-the-artefact-by-its-trim-not-by-its-bleed
- scope: generic
- status: candidate
- rule: When output is produced at one size and then trimmed to another, compute the **trim** content first and treat the sacrificial margin as material added outside it — never scale the content to fill the untrimmed box. Clamp the margin to what the source can supply and report what was achieved, so the drawn region always equals the drawn content. Assert that the trimmed result is identical regardless of which position on the sheet the item occupied.
- home: src/dixitgen/render/crop.py (`crop_with_bleed`), src/dixitgen/export/sheet_pdf.py (`_draw_front_page`), docs/ARCHITECTURE.md#the-trim-crop-is-the-card-bleed-is-extra-material-outside-it, tests/run_tests.py (`export: the cut card shows the preview's crop, identically in every slot`)
- evidence: art was scaled to fill the bled box (83x123mm) and then cut at 80x120mm, so a printed card was ~2.4% tighter than its preview on a 928x1232 source. Worse, bleed exists only on the block's outer edges, so slot (0,0) lost its left+top and slot (1,1) its right+bottom — the same card framed differently depending on its position, which also made a slot-independent preview impossible. Found by the author looking at a real exported PDF, not by any check: the gate asserted that placements *equalled* `art_box`, which is precisely the wrong invariant. The replacement asserts each placement *contains* its card box and stays within `art_box`.
- applications: 2026-09-23

## 2026-09-23 — state-the-structural-limit-instead-of-advising-a-workaround
- scope: generic
- status: candidate
- rule: Before telling the user to change their inputs to get a better result, check whether the algorithm can produce that result at all. Demonstrate the limit with a table over several inputs rather than reasoning about the one case in front of you.
- home: docs/ARCHITECTURE.md#four-side-bleed-is-structurally-impossible-here-and-that-is-fine
- evidence: advised the author to "render art slightly oversized to restore full bleed". Wrong: `crop_to_fill` is maximal, keeping 100% of the width or 100% of the height, so one axis never has a spare pixel and bleed on it is always zero — at any resolution. Checked across six source shapes (928x1232, 1200x1800, 1000x1300, 2048x2048, 3000x2000, 1500x2400): one spare column is zero in every case. The advice would have cost the author a re-render of their whole deck for no gain.
- applications: 2026-09-23

## 2026-09-23 — make-hidden-win-once-globally
- scope: generic
- status: candidate
- rule: Put `[hidden] { display: none !important; }` in the stylesheet once, at the top. The browser's own `[hidden]` rule lives in the UA stylesheet, so **any** author rule that sets `display` silently beats it and `el.hidden = true` stops hiding. Do not patch it per component. When a browser check waits for something to disappear, wait on `state="hidden"`, never on a `[hidden]` attribute selector.
- home: web/app.css (the `[hidden]` rule at the top), docs/ARCHITECTURE.md#hidden-needs-important-once-globally, tests/check_gallery.py (the `state="hidden"` waits)
- evidence: `.editor { display: grid }` left a closed editor on screen as an empty bordered box; `.dialog` had needed its own `.dialog[hidden] { display: none }` workaround for the same reason, which hid the general problem. Worse, the broken CSS made the test *pass*: `page.wait_for_selector("#editor[hidden]")` defaults to `state="visible"`, and the element really was still visible, so the wait succeeded and the bug shipped. The same wait against the correctly-hidden export dialog then timed out, which is what exposed both.
- applications: 2026-09-23

## 2026-09-23 — make-a-long-running-request-a-job-with-honest-progress
- scope: generic
- status: candidate
- rule: When an action takes long enough to need a progress indicator, do not hold the request open — start a worker, return an id, and poll. Drive the percentage from a callback the worker fires per unit of real work, never from a timer. Give the worker its own database session; sessions are not thread-safe.
- home: src/dixitgen/web/api.py (`ExportApi`), src/dixitgen/export/sheet_pdf.py (the `progress` callback), docs/ARCHITECTURE.md#dixitgenweb--web--the-overview, tests/run_tests.py (`export: progress is reported once per card drawn, and reaches the total`)
- evidence: exporting a deck is one large raster cropped and embedded per card; the synchronous POST gave the browser nothing to show for several seconds. The gate now asserts the progress sequence is `0..total` with one tick per image, so "80%" cannot drift into decoration.
- applications: 2026-09-23

## 2026-09-23 — a-committed-generated-file-prints-repo-relative-paths
- scope: generic
- status: candidate
- rule: Any generator whose output is committed (verify evidence, a report, a manifest) must format paths as `p.relative_to(ROOT).as_posix()`, and every example path quoted in a doc must be redacted. Run the tracked-file machine-path grep in CLAUDE.md before any push, and before making a repo public.
- home: CLAUDE.md#a-committed-generated-file-prints-repo-relative-paths, tests/run_tests.py (`main`, the `output :` header line)
- evidence: `tests/last-run.txt:5` carried `output : <drive>:\<repo>\out\verify` — committed since the verify gate first ran, and about to become world-readable in a PUBLIC GitHub repo. The seeded doctrine line ("no machine-specific absolute paths") already existed and did not prevent it, because nothing regenerated the check when the generator changed. N=1 file, 6 commits of history.
- applications: 2026-09-23

## 2026-09-23 — git-grep-ere-alternation-eats-a-trailing-backslash
- scope: generic
- status: candidate
- rule: In a `git grep -E` or `grep -E` pattern, write a literal backslash as the bracket expression `[\]`, never as `\\`. An alternative ending `\\|` silently degrades: the escaped pipe is read as a literal `|`, the alternation collapses to one branch, and the check exits 1 — indistinguishable from a real pass. Never trust an exit 1 from a grep-based check that has not been shown to exit 0 on a planted positive fixture.
- home: CLAUDE.md#a-committed-generated-file-prints-repo-relative-paths (the verification step and its two warnings)
- evidence: the pattern `'[A-Za-z]:\\[^\\]*\\|...'` returned exit 1 against a repo that did contain an absolute path; stripping the alternation surfaced the real cause, `fatal: command line, '[A-Za-z]:\[^\]*\': Trailing backslash`. Separately, `printf` mangles path fixtures (`\v` becomes a vertical tab, so `out\verify` became `out^Kerify`) — build path fixtures with a quoted heredoc.
- applications: 2026-09-23
