"""Drive the overview in a real browser.

    python tests/check_gallery.py

This is the frontend's check, deliberately separate from the verify gate:
exporting a PDF proves nothing about the browser UI, and rendering cards proves
nothing about the geometry.  PROJECT.md keeps ``web/**`` out of
``source_globs`` for exactly that reason.

**It writes.**  It uploads cards, edits them, exports and deletes.  So it
refuses to run against the author's real library and says how to fix that --
``data/cards.db`` holds the only copy of every image, and deletion here is
permanent.

Where it points
---------------
``DIXIT_URL`` if set -- you are then responsible for having started that server
against a scratch database (``serve.bat`` takes a port; the CLI takes
``--db``).  With nothing set, it starts its own server on **8776** with a
scratch database and stops it again, which is the normal path and the one
CLAUDE.md's server rule describes.
"""

from __future__ import annotations

import io
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image  # noqa: E402

#: Claude's throwaway port.  8775 is the author's and is never started here.
CHECK_PORT = 8776
SCRATCH_DB = ROOT / "out" / "verify" / "gallery-check.db"
SERVER_LOG = ROOT / "out" / "verify" / "gallery-check-server.log"
FIXTURE_DIR = ROOT / "out" / "verify" / "gallery-fixtures"

_RESULTS: List[Tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    _RESULTS.append((name, ok, detail))
    print("{} {}".format("PASS" if ok else "FAIL", name))
    if detail:
        print("     {}".format(detail))


def equal(got, want, what: str) -> None:
    if got != want:
        raise AssertionError("{}: got {!r}, expected {!r}".format(what, got, want))


def make_fixtures() -> List[Path]:
    """Images on disk, because the upload goes through a real file input."""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    palette = [(200, 60, 60), (60, 170, 90), (70, 110, 210)]
    for i, colour in enumerate(palette):
        # Square on purpose: a square source has crop freedom, so the drag can
        # actually move something.  A 2:3 source would be uncroppable and the
        # crop check would pass for any implementation.
        img = Image.new("RGB", (1400, 1400), colour)
        img.paste((250, 240, 40), (0, 0, 466, 1400))  # a left band to aim at
        path = FIXTURE_DIR / "fixture_{}.png".format(i)
        img.save(path)
        paths.append(path)
    back = Image.new("RGB", (1200, 1800), (30, 30, 60))
    back_path = FIXTURE_DIR / "back.png"
    back.save(back_path)
    paths.append(back_path)
    return paths


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def port_is_open(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.4)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def start_server() -> Tuple[str, Optional[subprocess.Popen]]:
    """Return (base_url, process). The process is None when reusing DIXIT_URL."""
    external = os.environ.get("DIXIT_URL")
    if external:
        return external.rstrip("/"), None

    if port_is_open(CHECK_PORT):
        raise SystemExit(
            "port {} is already in use. That is Claude's throwaway port; stop "
            "it with `stop-server.bat {}` or set DIXIT_URL to point this check "
            "somewhere else.".format(CHECK_PORT, CHECK_PORT)
        )

    SCRATCH_DB.parent.mkdir(parents=True, exist_ok=True)
    if SCRATCH_DB.exists():
        SCRATCH_DB.unlink()

    # The server's output goes to a FILE, never to an unread pipe.
    #
    # CherryPy logs one line per request. With stdout=PIPE and nobody reading
    # it, the OS pipe buffer (~64KB on Windows) fills partway through the
    # first page load -- nine ES modules, a stylesheet and several API calls --
    # and the server then blocks forever on its own log write. The symptom is
    # maddening: the page half-loads, the console is silent, and every
    # selector times out. A file has no such limit, and the check can print
    # its tail when something fails.
    SERVER_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_handle = open(SERVER_LOG, "w", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "dixitgen.cli",
            "serve",
            "--port",
            str(CHECK_PORT),
            "--db",
            "sqlite:///{}".format(SCRATCH_DB.as_posix()),
        ],
        cwd=str(ROOT),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )
    base = "http://127.0.0.1:{}".format(CHECK_PORT)
    for _ in range(100):
        if process.poll() is not None:
            raise SystemExit(
                "the server exited before answering:\n{}".format(_server_log_tail())
            )
        try:
            get_json(base + "/api/meta")
            return base, process
        except (urllib.error.URLError, OSError, ValueError):
            time.sleep(0.2)
    process.terminate()
    raise SystemExit("the server did not answer on {} within 20s".format(base))


def _server_log_tail(lines: int = 25) -> str:
    try:
        return "\n".join(SERVER_LOG.read_text(encoding="utf-8").splitlines()[-lines:])
    except OSError:
        return "(no server log)"


def guard_library(base: str) -> None:
    meta = get_json(base + "/api/meta")
    if meta.get("is_default_library") and not os.environ.get("DIXIT_ALLOW_LIBRARY"):
        raise SystemExit(
            "REFUSING TO RUN: {} is serving the real card library.\n"
            "This check uploads, edits and DELETES cards, and deletion is "
            "permanent.\n"
            "Start a throwaway instead:\n"
            "    python -m dixitgen.cli serve --port 8776 --db "
            "sqlite:///out/verify/gallery-check.db\n"
            "then re-run with DIXIT_URL=http://127.0.0.1:8776 — or run this "
            "with nothing set and it will do that for you.".format(base)
        )


def run_checks(page, base: str, fixtures: List[Path]) -> None:
    cards = [str(p) for p in fixtures if p.name.startswith("fixture_")]
    back = str([p for p in fixtures if p.name == "back.png"][0])

    # -- the page loads and reads its numbers from the API -----------------
    page.goto(base + "/web/index.html")
    # Wait for the app to say it is ready, not for an element to exist:
    # #spec-line and #grid are both in the static HTML, so waiting on them
    # races the fetches and passes by luck.
    page.wait_for_selector("body[data-ready='true']", timeout=20000)
    spec_text = page.inner_text("#spec-line")
    meta = get_json(base + "/api/meta")
    if meta["card"]["label"] not in spec_text:
        raise AssertionError(
            "the header does not show the card format from /api/meta: {!r}".format(spec_text)
        )
    record("overview: loads and shows the spec from /api/meta", True)

    # -- upload ------------------------------------------------------------
    page.fill("#upload-tag", "deck one")
    page.set_input_files("#file-input", cards)
    page.wait_for_selector(".tile", timeout=15000)
    page.wait_for_function(
        "document.querySelectorAll('.tile').length === %d" % len(cards), timeout=15000
    )
    equal(len(page.query_selector_all(".tile")), len(cards), "tiles after upload")
    record("upload: three files become three tiles", True)

    # The tag typed before the drop is applied to every file in it.
    tags = get_json(base + "/api/tags")["tags"]
    names = {tag["name"]: tag["count"] for tag in tags}
    equal(names.get("deck one"), len(cards), "cards carrying the upload tag")
    record("upload: the upload tag is applied to the whole drop", True)

    # -- selection ---------------------------------------------------------
    page.click(".tile:nth-child(1)")
    page.click(".tile:nth-child(3)")
    page.wait_for_function("document.querySelectorAll('.tile.is-selected').length === 2")
    if "2 selected" not in page.inner_text("#selection-count"):
        raise AssertionError("the count does not report 2 selected")
    # The order badge shows the selection order, which is the print order.
    badges = [node.inner_text() for node in page.query_selector_all(".tile-order")]
    equal(sorted(badges), ["1", "2"], "selection order badges")
    record("selection: clicking marks cards and numbers them in pick order", True)

    if page.is_disabled("#export-open"):
        raise AssertionError("Export is still disabled with two cards selected")

    # -- the crop editor ---------------------------------------------------
    page.hover(".tile:nth-child(1)")
    page.click(".tile:nth-child(1) .tile-edit")
    page.wait_for_selector("#crop-window")
    page.wait_for_function(
        "document.querySelector('#crop-hint') && "
        "document.querySelector('#crop-hint').dataset.free === 'true'",
        timeout=10000,
    )
    before = page.inner_text("#crop-readout")

    box = page.query_selector("#crop-window").bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] / 2 + 120, box["y"] + box["height"] / 2, steps=12)
    page.mouse.up()
    after = page.inner_text("#crop-readout")
    if before == after:
        raise AssertionError(
            "dragging the crop window did not change the focus readout "
            "(still {!r}) -- the source is square, so it has crop freedom".format(before)
        )
    record("editor: dragging the picture moves the crop focus", True)

    page.fill("#edit-name", "renamed by the check")
    page.click("#edit-save")
    page.wait_for_selector("#editor", state="hidden")
    page.wait_for_function(
        "[...document.querySelectorAll('.tile-name')]"
        ".some(n => n.textContent.includes('renamed by the check'))",
        timeout=10000,
    )
    stored = get_json(base + "/api/cards")["cards"]
    renamed = [card for card in stored if card["name"] == "renamed by the check"]
    equal(len(renamed), 1, "renamed cards")
    if renamed[0]["focus"]["x"] == 0.5:
        raise AssertionError("the dragged focus was not saved: still 0.5")
    record("editor: the name and the dragged focus both persist", True)

    # -- filtering ---------------------------------------------------------
    page.fill("#filter-q", "renamed")
    page.wait_for_function("document.querySelectorAll('.tile').length === 1", timeout=10000)
    record("filter: searching names narrows the grid", True)
    page.fill("#filter-q", "")
    page.wait_for_function(
        "document.querySelectorAll('.tile').length === %d" % len(cards), timeout=10000
    )

    # -- backs -------------------------------------------------------------
    page.set_input_files("#back-input", [back])
    page.wait_for_selector(".back-tile", timeout=15000)
    equal(len(get_json(base + "/api/backs")["backs"]), 1, "backs on the shelf")
    equal(len(page.query_selector_all(".tile")), len(cards), "a back must not join the card grid")
    record("backs: a back lands on its own shelf, never in the card grid", True)

    # A back is an image with a name and a crop, so it gets the same editor.
    page.hover(".back-tile")
    page.click(".back-tile .tile-edit")
    page.wait_for_selector("#crop-window")
    if page.query_selector("#edit-tags") is not None:
        raise AssertionError("a back has no tags, but the editor offered the field")
    page.wait_for_function(
        "document.querySelector('#crop-hint') && "
        "document.querySelector('#crop-hint').dataset.free === 'true'",
        timeout=10000,
    )
    box = page.query_selector("#crop-window").bounding_box()
    before = page.inner_text("#crop-readout")
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] / 2 + 100, box["y"] + box["height"] / 2, steps=10)
    page.mouse.up()
    if page.inner_text("#crop-readout") == before:
        raise AssertionError("dragging a back's crop did not move its focus")
    page.fill("#edit-name", "renamed back")
    page.click("#edit-save")
    page.wait_for_selector("#editor", state="hidden")
    stored = get_json(base + "/api/backs")["backs"][0]
    equal(stored["name"], "renamed back", "back name after editing")
    if stored["focus"]["x"] == 0.5:
        raise AssertionError("the dragged focus was not saved on the back")
    record("backs: renaming and re-cropping a back works like a card", True)

    # -- export ------------------------------------------------------------
    page.click("#select-all")
    page.click("#export-open")
    page.wait_for_selector("#export-dialog:not([hidden])")

    # The dialog must not scroll sideways. A form control's intrinsic minimum
    # width used to push the panel wider than its own box.
    overflow = page.evaluate(
        "() => { const p = document.querySelector('.dialog-panel');"
        " return {scroll: p.scrollWidth, client: p.clientWidth}; }"
    )
    if overflow["scroll"] > overflow["client"] + 1:
        raise AssertionError(
            "the export dialog scrolls horizontally: content {}px in a {}px "
            "panel".format(overflow["scroll"], overflow["client"])
        )
    record("export: the dialog has no horizontal scrollbar", True)

    summary = page.inner_text(".export-summary")
    per_sheet = meta["sheet"]["cards_per_sheet"]
    expected_sheets = -(-len(cards) // per_sheet)
    if str(expected_sheets) not in summary:
        raise AssertionError(
            "the dialog predicts the wrong sheet count: {!r} for {} cards at "
            "{} per sheet".format(summary, len(cards), per_sheet)
        )
    page.select_option("#export-back", index=1)
    page.fill("#export-name", "gallery-check")
    page.click("#export-run")

    # The dialog goes at once; the notification carries the job from here.
    page.wait_for_selector("#export-dialog", state="hidden", timeout=5000)
    record("export: the dialog closes as soon as the job starts", True)

    page.wait_for_selector(".toast", timeout=5000)
    page.wait_for_selector(".toast-success", timeout=60000)
    toast = page.query_selector(".toast-success")
    text = toast.inner_text()
    if "Batch exported" not in text:
        raise AssertionError("the finished notification reads {!r}".format(text))
    record("export: progress notification becomes 'Batch exported'", True)

    links = toast.query_selector_all(".toast-action")
    labels = [node.inner_text().strip() for node in links]
    if labels != ["Download", "Open"]:
        raise AssertionError(
            "expected Download and Open on one line, got {}".format(labels)
        )
    href = links[1].get_attribute("href")
    with urllib.request.urlopen(base + href, timeout=15) as response:
        head = response.read(5)
    equal(head, b"%PDF-", "the Open link really serves a PDF")
    download_href = links[0].get_attribute("href")
    if "download" not in download_href:
        raise AssertionError(
            "the Download link should ask for an attachment: {}".format(download_href)
        )
    record("export: Download and Open sit on one line and both resolve", True)

    # Every notification can be dismissed, and the layer leaves nothing behind.
    for _ in range(len(page.query_selector_all(".toast"))):
        page.click(".toast .toast-close")
        page.wait_for_timeout(60)
    equal(len(page.query_selector_all(".toast")), 0, "notifications after dismissing")
    record("notifications: each can be closed with its own X", True)

    # -- delete ------------------------------------------------------------
    page.once("dialog", lambda dialog: dialog.accept())
    page.hover(".tile:nth-child(1)")
    page.click(".tile:nth-child(1) .tile-edit")
    page.wait_for_selector("#edit-delete")
    page.once("dialog", lambda dialog: dialog.accept())
    page.click("#edit-delete")
    page.wait_for_function(
        "document.querySelectorAll('.tile').length === %d" % (len(cards) - 1), timeout=10000
    )
    equal(len(get_json(base + "/api/cards")["cards"]), len(cards) - 1, "cards after delete")
    record("delete: confirming removes the card from the library", True)


def _diagnose(page, console: List[str]) -> None:
    """Say what the page actually looked like when a check failed.

    A browser check that reports only "selector not found" sends the next
    person hunting blind. The page's own status bar usually already holds the
    answer -- the client puts every API error there.
    """
    print("-" * 72)
    try:
        toasts = page.query_selector_all(".toast")
        if toasts:
            print("notifications   :")
            for node in toasts:
                print("    {!r}".format(" | ".join(node.inner_text().split("\n"))))
        else:
            print("notifications   : (none)")
    except Exception:  # noqa: BLE001
        print("notifications   : unreadable")
    try:
        print("tiles on page   : {}".format(len(page.query_selector_all(".tile"))))
        print("grid says       : {!r}".format(page.inner_text("#grid")[:200]))
    except Exception:  # noqa: BLE001
        pass
    if console:
        print("browser console :")
        for line in console[:20]:
            print("    {}".format(line))
    else:
        print("browser console : (silent)")
    if SERVER_LOG.exists():
        print("server log tail :")
        for line in _server_log_tail().splitlines():
            print("    {}".format(line))
    shot = FIXTURE_DIR.parent / "gallery-check-failure.png"
    try:
        page.screenshot(path=str(shot))
        print("screenshot      : {}".format(shot))
    except Exception:  # noqa: BLE001
        pass
    print("-" * 72)


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "playwright is not installed, so the browser check cannot run.\n"
            "    pip install playwright && python -m playwright install chromium"
        )
        return 2

    fixtures = make_fixtures()
    base, process = start_server()
    print("checking {}{}".format(base, "" if process else "  (reusing DIXIT_URL)"))

    try:
        guard_library(base)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1400, "height": 1000})
            console: List[str] = []
            page.on("console", lambda m: console.append("[{}] {}".format(m.type, m.text)))
            page.on("pageerror", lambda exc: console.append("[pageerror] {}".format(exc)))
            page.on(
                "requestfailed",
                lambda req: console.append("[requestfailed] {} {}".format(req.url, req.failure)),
            )
            try:
                run_checks(page, base, fixtures)
            except Exception as exc:  # noqa: BLE001 -- report, do not crash
                import traceback

                traceback.print_exc()
                record("browser run", False, "{}: {}".format(type(exc).__name__, exc))
                _diagnose(page, console)
            finally:
                browser.close()
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()

    passed = [r for r in _RESULTS if r[1]]
    failed = [r for r in _RESULTS if not r[1]]
    print("=" * 72)
    print("{} passed, {} failed, {} total".format(len(passed), len(failed), len(_RESULTS)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
