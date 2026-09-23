"""The JSON API the browser overview talks to.

Shape
-----
    GET    /api/meta                  the print spec -- the frontend's only
                                      source of measurements
    GET    /api/cards?tag=&q=         the library, newest first
    POST   /api/cards/upload          multipart; one or many files at once
    GET    /api/cards/{id}            one card
    PUT    /api/cards/{id}            {name, notes, tags}
    DELETE /api/cards/{id}            permanent
    PUT    /api/cards/{id}/focus      {x, y} -- also regenerates the thumbnail
    GET    /api/cards/{id}/thumb      grid tile (JPEG, already print-cropped)
    GET    /api/cards/{id}/image      the original upload, untouched
    GET    /api/tags                  [{name, count}]
    GET    /api/backs                 the backs shelf
    POST   /api/backs/upload
    GET    /api/backs/{id}/thumb
    DELETE /api/backs/{id}
    PUT    /api/backs/{id}            {name}
    PUT    /api/backs/{id}/focus      {x, y}
    GET    /api/backs/{id}/image      the original upload
    POST   /api/export                starts a job; 202 with {job_id}
                                      {format} picks sheets or images
    GET    /api/export/status/{id}    {state, done, total, percent, files}
    GET    /api/export/file/{name}    the PDF or zip; ?download=1 to save

Errors come back as JSON (``{"error": "..."}``), never CherryPy's HTML page:
the browser client shows the message, and an HTML body in a fetch() is just a
blank failure.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import List, Optional

import cherrypy

from .. import store
from ..export.card_images import export_card_images
from ..export.formats import OUTPUTS, OutputFormat, option_for
from ..export.sheet_pdf import export_batch
from ..spec import DIXIT, SHEET, Flip, GeometryError

#: Where exports are written. Gitignored; see .gitignore.
EXPORT_DIR = Path(__file__).resolve().parents[3] / "out"

#: A generated filename must survive being put in a URL and a Windows path.
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")

#: What ``/api/export/file`` will serve, keyed by suffix.  The suffixes come
#: from the format table rather than being listed here, so a new output format
#: is downloadable the day it exists -- and the assertion below turns "added a
#: format, forgot its media type" into an import-time failure instead of a 404
#: the user meets after waiting for an export.
DOWNLOAD_MIME = {".pdf": "application/pdf", ".zip": "application/zip"}
assert {option.suffix for option in OUTPUTS.values()} <= set(DOWNLOAD_MIME), (
    "an output format has a suffix DOWNLOAD_MIME cannot serve"
)


def json_error(status, message, traceback, version):  # noqa: ARG001 - cherrypy hook
    """Render every error as JSON. Wired into the config in ``app.serve``.

    CherryPy's default error page is HTML, which inside a ``fetch()`` is an
    unreadable blank failure -- the client can only say "something went
    wrong". This hands it the actual message.
    """
    cherrypy.response.headers["Content-Type"] = "application/json"
    return json.dumps({"error": message or status, "status": status})


def _fail(status: int, message: str):
    raise cherrypy.HTTPError(status, message)


def _require(method: str) -> None:
    if cherrypy.request.method != method:
        _fail(405, "this endpoint takes {}, not {}".format(method, cherrypy.request.method))


def _body() -> dict:
    """The request's JSON body, or {} -- never an exception on an empty body."""
    data = getattr(cherrypy.request, "json", None)
    return data if isinstance(data, dict) else {}


def _parts(value) -> List:
    """CherryPy hands one file part for a single upload and a list for many."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


# ---------------------------------------------------------------------------
# serialisation
# ---------------------------------------------------------------------------

#: The box a card's art is actually drawn into. Every slot of a 2x2 grid sits
#: on the block edge, so all four are the bled size; taking slot (0,0) is the
#: largest case and therefore the conservative one for a soft-art warning.
def _art_box():
    return SHEET.art_box(0, 0)


def card_json(card: store.Card) -> dict:
    box = _art_box()
    return {
        "id": card.id,
        "name": card.name,
        "notes": card.notes,
        "tags": sorted(tag.name for tag in card.tags),
        "src_w": card.src_w,
        "src_h": card.src_h,
        "mime": card.image_mime,
        "focus": {"x": card.focus_x, "y": card.focus_y},
        "soft": DIXIT.art_is_soft(card.src_w, card.src_h, box.w_mm, box.h_mm),
        "created": card.created_at.isoformat() if card.created_at else None,
        "thumb_url": "/api/cards/{}/thumb".format(card.id),
        "image_url": "/api/cards/{}/image".format(card.id),
    }


def back_json(back: store.Back) -> dict:
    box = _art_box()
    return {
        "id": back.id,
        "name": back.name,
        "src_w": back.src_w,
        "src_h": back.src_h,
        "soft": DIXIT.art_is_soft(back.src_w, back.src_h, box.w_mm, box.h_mm),
        "focus": {"x": back.focus_x, "y": back.focus_y},
        "created": back.created_at.isoformat() if back.created_at else None,
        "thumb_url": "/api/backs/{}/thumb".format(back.id),
        "image_url": "/api/backs/{}/image".format(back.id),
    }


def _json(payload) -> bytes:
    """Encode a JSON response by hand.

    The ``default`` handlers return *either* JSON *or* raw image bytes
    depending on the path segment, so they cannot carry the ``json_out`` tool
    -- it would try to serialise a JPEG. One helper, used explicitly, keeps
    both branches honest.
    """
    cherrypy.response.headers["Content-Type"] = "application/json"
    return json.dumps(payload).encode("utf-8")


def _serve_bytes(data: bytes, mime: str, filename: Optional[str] = None) -> bytes:
    cherrypy.response.headers["Content-Type"] = mime
    if filename:
        cherrypy.response.headers["Content-Disposition"] = (
            'attachment; filename="{}"'.format(filename)
        )
    return data


# ---------------------------------------------------------------------------
# resources
# ---------------------------------------------------------------------------


class CardsApi:
    def __init__(self, engine):
        self.engine = engine

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def index(self, tag: Optional[str] = None, q: Optional[str] = None):
        _require("GET")
        with store.session_scope(self.engine) as session:
            cards = store.list_cards(session, tag=tag or None, search=q or None)
            return {"cards": [card_json(card) for card in cards]}

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def upload(self, files=None, tag: Optional[str] = None, **_ignored):
        """Multipart upload of one or many images.

        ``tag`` is applied to every file in the drop -- the common case is
        dragging a folder in and wanting them all marked "deck 1".
        """
        _require("POST")
        parts = _parts(files)
        if not parts:
            _fail(400, "no files in the upload")

        created, skipped = [], []
        tags = [tag] if tag and tag.strip() else []
        with store.session_scope(self.engine) as session:
            for part in parts:
                raw_name = getattr(part, "filename", "") or "untitled"
                data = part.file.read() if hasattr(part, "file") else bytes(part)
                name = Path(raw_name).stem.replace("_", " ").strip() or "untitled"
                try:
                    card = store.add_card(session, data, name=name, tags=tags)
                except store.StoreError as exc:
                    # One bad file must not lose the rest of the drop.
                    skipped.append({"name": raw_name, "reason": str(exc)})
                    continue
                created.append(card_json(card))
        return {"created": created, "skipped": skipped}

    @cherrypy.expose
    @cherrypy.tools.json_in(force=False)
    def default(self, card_id: str, action: Optional[str] = None, **_ignored):
        try:
            ident = int(card_id)
        except ValueError:
            _fail(404, "not a card id: {!r}".format(card_id))

        method = cherrypy.request.method
        with store.session_scope(self.engine) as session:
            try:
                card = store.get_card(session, ident)
            except store.StoreError as exc:
                _fail(404, str(exc))

            if action == "thumb":
                _require("GET")
                cherrypy.response.headers["Cache-Control"] = "no-cache"
                return _serve_bytes(card.thumb, "image/jpeg")

            if action == "image":
                _require("GET")
                return _serve_bytes(card.image, card.image_mime)

            if action == "focus":
                _require("PUT")
                body = _body()
                try:
                    focus = (float(body.get("x", 0.5)), float(body.get("y", 0.5)))
                except (TypeError, ValueError):
                    _fail(400, "focus needs numeric x and y")
                return _json(card_json(store.set_focus(session, ident, focus)))

            if action is not None:
                _fail(404, "no such action: {}".format(action))

            if method == "GET":
                return _json(card_json(card))
            if method == "PUT":
                body = _body()
                tags = body.get("tags")
                return _json(
                    card_json(
                        store.update_card(
                            session,
                            ident,
                            name=body.get("name"),
                            notes=body.get("notes"),
                            tags=list(tags) if tags is not None else None,
                        )
                    )
                )
            if method == "DELETE":
                store.delete_card(session, ident)
                return _json({"deleted": ident})
            _fail(405, "{} not allowed here".format(method))


class BacksApi:
    def __init__(self, engine):
        self.engine = engine

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def index(self):
        _require("GET")
        with store.session_scope(self.engine) as session:
            return {"backs": [back_json(back) for back in store.list_backs(session)]}

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def upload(self, files=None, **_ignored):
        _require("POST")
        parts = _parts(files)
        if not parts:
            _fail(400, "no files in the upload")
        created, skipped = [], []
        with store.session_scope(self.engine) as session:
            for part in parts:
                raw_name = getattr(part, "filename", "") or "untitled"
                data = part.file.read() if hasattr(part, "file") else bytes(part)
                name = Path(raw_name).stem.replace("_", " ").strip() or "untitled"
                try:
                    back = store.add_back(session, data, name=name)
                except store.StoreError as exc:
                    skipped.append({"name": raw_name, "reason": str(exc)})
                    continue
                created.append(back_json(back))
        return {"created": created, "skipped": skipped}

    @cherrypy.expose
    @cherrypy.tools.json_in(force=False)
    def default(self, back_id: str, action: Optional[str] = None, **_ignored):
        try:
            ident = int(back_id)
        except ValueError:
            _fail(404, "not a back id: {!r}".format(back_id))
        with store.session_scope(self.engine) as session:
            try:
                back = store.get_back(session, ident)
            except store.StoreError as exc:
                _fail(404, str(exc))
            if action == "thumb":
                _require("GET")
                cherrypy.response.headers["Cache-Control"] = "no-cache"
                return _serve_bytes(back.thumb, "image/jpeg")

            if action == "image":
                _require("GET")
                return _serve_bytes(back.image, back.image_mime)

            if action == "focus":
                _require("PUT")
                body = _body()
                try:
                    focus = (float(body.get("x", 0.5)), float(body.get("y", 0.5)))
                except (TypeError, ValueError):
                    _fail(400, "focus needs numeric x and y")
                return _json(back_json(store.set_back_focus(session, ident, focus)))

            if action is not None:
                _fail(404, "no such action: {}".format(action))

            method = cherrypy.request.method
            if method == "DELETE":
                store.delete_back(session, ident)
                return _json({"deleted": ident})
            if method == "GET":
                return _json(back_json(back))
            if method == "PUT":
                body = _body()
                return _json(
                    back_json(store.update_back(session, ident, name=body.get("name")))
                )
            _fail(405, "{} not allowed here".format(method))


class TagsApi:
    def __init__(self, engine):
        self.engine = engine

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def index(self):
        _require("GET")
        with store.session_scope(self.engine) as session:
            return {
                "tags": [
                    {"name": name, "count": count}
                    for name, count in store.all_tags(session)
                ]
            }


class ExportApi:
    """Export runs as a background job, so the browser can show real progress.

    A deck of eighty cards is eighty large rasters cropped and embedded; doing
    that inside the POST would hold the request open for many seconds with
    nothing to show for it. Instead the POST starts a worker and returns a job
    id straight away, and the client polls ``/api/export/status/<id>``.

    The progress number is honest -- ``export_batch`` counts each card actually
    drawn, front or back -- rather than an animation timed to finish when the
    request does.
    """

    #: How many finished jobs to remember, so a client that polls late still
    #: gets its answer. Oldest are dropped first.
    MAX_JOBS = 20

    def __init__(self, engine):
        self.engine = engine
        self._jobs = OrderedDict()
        self._lock = threading.Lock()

    # -- job bookkeeping ---------------------------------------------------
    def _put(self, job_id: str, **fields) -> None:
        with self._lock:
            job = self._jobs.get(job_id, {})
            job.update(fields)
            self._jobs[job_id] = job
            self._jobs.move_to_end(job_id)
            while len(self._jobs) > self.MAX_JOBS:
                self._jobs.popitem(last=False)

    def _get(self, job_id: str) -> Optional[dict]:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    # -- starting ----------------------------------------------------------
    @cherrypy.expose
    @cherrypy.tools.json_in(force=False)
    @cherrypy.tools.json_out()
    def index(self):
        _require("POST")
        body = _body()
        card_ids = body.get("card_ids") or []
        if not card_ids:
            _fail(400, "select at least one card to export")

        format_value = body.get("format", OutputFormat.A4_PDF.value)
        try:
            option = option_for(format_value)
        except (KeyError, ValueError):
            _fail(400, "unknown output format {!r}".format(format_value))

        # Duplex mode is parsed even for an image export -- it is ignored
        # there, but a payload carrying a bad one should still be a 400
        # rather than silently doing something else.
        flip_value = body.get("flip", Flip.LONG_EDGE.value)
        try:
            flip = Flip(flip_value)
        except ValueError:
            _fail(400, "unknown duplex mode {!r}".format(flip_value))

        offset = body.get("offset_mm") or {}
        try:
            offset_mm = (float(offset.get("x", 0.0)), float(offset.get("y", 0.0)))
        except (TypeError, ValueError):
            _fail(400, "offset_mm needs numeric x and y")

        name = str(body.get("name") or "batch")
        name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-") or "batch"
        out_path = EXPORT_DIR / "{}{}".format(name, option.suffix)

        try:
            ids = [int(i) for i in card_ids]
        except (TypeError, ValueError):
            _fail(400, "card_ids must be numbers")
        back_id = body.get("back_id")
        back_id = int(back_id) if back_id else None

        # Validate against the library before promising a job: a bad id should
        # be a 400 seen immediately, not a job that fails a second later.
        with store.session_scope(self.engine) as session:
            try:
                store.list_cards(session, ids=ids)
                if back_id:
                    store.get_back(session, back_id)
            except store.StoreError as exc:
                _fail(400, str(exc))

        # One drawn card is the unit either way; a sheet export draws the back
        # once per card, an image export writes one shared back file.
        if option.kind == "images":
            total = len(ids) + (1 if back_id else 0)
        else:
            total = len(ids) * (2 if back_id else 1)

        job_id = uuid.uuid4().hex
        self._put(
            job_id,
            state="running",
            done=0,
            total=total,
            files=[],
            warnings=[],
            error=None,
            started=time.time(),
            name=name,
            format=option.id,
        )

        worker = threading.Thread(
            target=self._run,
            args=(job_id, ids, back_id, out_path, flip, offset_mm, option),
            daemon=True,
            name="export-{}".format(job_id[:8]),
        )
        worker.start()

        cherrypy.response.status = 202
        return {
            "job_id": job_id,
            "format": option.id,
            "status_url": "/api/export/status/{}".format(job_id),
        }

    def _run(self, job_id, ids, back_id, out_path, flip, offset_mm, option) -> None:
        """The worker. Opens its own session -- sessions are not thread-safe."""
        try:
            with store.session_scope(self.engine) as session:
                cards = store.batch_for_export(session, ids)
                back_image = None
                back_focus = (0.5, 0.5)
                if back_id:
                    back = store.get_back(session, back_id)
                    back_image = store.to_back_image(back)
                    back_focus = back.focus

            def progress(done, total):
                self._put(job_id, done=done, total=total)

            if option.kind == "images":
                # No sheets, so no duplex pass and no calibration offset --
                # those describe a piece of paper being turned over.
                result = export_card_images(
                    cards,
                    out_path,
                    option,
                    back=back_image,
                    back_focus=back_focus,
                    progress=progress,
                )
            else:
                result = export_batch(
                    cards,
                    out_path,
                    back=back_image,
                    flip=flip,
                    offset_mm=offset_mm,
                    back_focus=back_focus,
                    progress=progress,
                )
        except GeometryError as exc:
            self._put(
                job_id,
                state="error",
                error="the layout would not register, so nothing was written: {}".format(exc),
            )
        except Exception as exc:  # noqa: BLE001 -- the job reports, never crashes
            self._put(
                job_id,
                state="error",
                error="{}: {}".format(type(exc).__name__, exc),
            )
        else:
            self._put(
                job_id,
                state="done",
                sheets=result.sheets,
                cards=result.cards,
                images=result.images,
                flip=result.flip.value if result.flip else None,
                warnings=result.warnings,
                files=[
                    {
                        "name": path.name,
                        "size": path.stat().st_size,
                        "url": "/api/export/file/{}".format(path.name),
                        "download_url": "/api/export/file/{}?download=1".format(path.name),
                    }
                    for path in result.paths
                ],
            )

    # -- polling -----------------------------------------------------------
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def status(self, job_id: str):
        _require("GET")
        job = self._get(job_id)
        if job is None:
            _fail(404, "no such export job (it may have aged out)")
        total = job.get("total") or 0
        done = job.get("done") or 0
        job["percent"] = round(100 * done / total) if total else 0
        return job

    # -- serving the result ------------------------------------------------
    @cherrypy.expose
    def file(self, filename: str, download: Optional[str] = None):
        """Serve a written export back to the browser.

        Inline by default, so "Open" shows a PDF in the browser's viewer;
        ``?download=1`` attaches it, so "Download" saves it.  A zip has nothing
        to show inline, and the frontend offers only Download for one.

        The media type is looked up by suffix in ``DOWNLOAD_MIME``, whose keys
        cover every format in the export table -- checked at import.

        The name is matched against a strict whitelist rather than joined and
        hoped for: this process can read the whole disk, and a path like
        ``..%2f..%2fcards.db`` must not resolve.
        """
        _require("GET")
        mime = DOWNLOAD_MIME.get(Path(filename).suffix.lower())
        if not SAFE_NAME.match(filename) or mime is None:
            _fail(404, "no such export")
        path = (EXPORT_DIR / filename).resolve()
        if path.parent != EXPORT_DIR.resolve() or not path.is_file():
            _fail(404, "no such export")
        return _serve_bytes(
            path.read_bytes(),
            mime,
            filename if download else None,
        )
