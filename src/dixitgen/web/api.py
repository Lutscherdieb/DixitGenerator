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
    POST   /api/export                {card_ids, back_id, flip, offset_mm}
    GET    /api/export/file/{name}    download a written PDF

Errors come back as JSON (``{"error": "..."}``), never CherryPy's HTML page:
the browser client shows the message, and an HTML body in a fetch() is just a
blank failure.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional

import cherrypy

from .. import store
from ..export.sheet_pdf import export_batch
from ..spec import DIXIT, SHEET, Flip, GeometryError

#: Where exports are written. Gitignored; see .gitignore.
EXPORT_DIR = Path(__file__).resolve().parents[3] / "out"

#: A generated filename must survive being put in a URL and a Windows path.
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")


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
        "created": back.created_at.isoformat() if back.created_at else None,
        "thumb_url": "/api/backs/{}/thumb".format(back.id),
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
                return _serve_bytes(back.thumb, "image/jpeg")
            if action is not None:
                _fail(404, "no such action: {}".format(action))
            if cherrypy.request.method == "DELETE":
                store.delete_back(session, ident)
                return _json({"deleted": ident})
            if cherrypy.request.method == "GET":
                return _json(back_json(back))
            _fail(405, "{} not allowed here".format(cherrypy.request.method))


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
    def __init__(self, engine):
        self.engine = engine

    @cherrypy.expose
    @cherrypy.tools.json_in(force=False)
    @cherrypy.tools.json_out()
    def index(self):
        _require("POST")
        body = _body()
        card_ids = body.get("card_ids") or []
        if not card_ids:
            _fail(400, "select at least one card to export")

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
        out_path = EXPORT_DIR / "{}.pdf".format(name)

        with store.session_scope(self.engine) as session:
            try:
                cards = store.batch_for_export(session, [int(i) for i in card_ids])
            except (store.StoreError, ValueError) as exc:
                _fail(400, str(exc))

            back_image = None
            back_id = body.get("back_id")
            if back_id:
                try:
                    back_image = store.to_back_image(
                        store.get_back(session, int(back_id))
                    )
                except (store.StoreError, ValueError) as exc:
                    _fail(400, str(exc))

            try:
                result = export_batch(
                    cards,
                    out_path,
                    back=back_image,
                    flip=flip,
                    offset_mm=offset_mm,
                )
            except GeometryError as exc:
                # The export refused to write. Say so plainly: this is the
                # assertion PROJECT.md promises, not a crash.
                _fail(500, "the layout would not register, so nothing was written: {}".format(exc))

        return {
            "sheets": result.sheets,
            "cards": result.cards,
            "flip": result.flip.value,
            "warnings": result.warnings,
            "files": [
                {
                    "name": path.name,
                    "size": path.stat().st_size,
                    "url": "/api/export/file/{}".format(path.name),
                }
                for path in result.paths
            ],
        }

    @cherrypy.expose
    def file(self, filename: str):
        """Serve a written PDF back to the browser.

        The name is matched against a strict whitelist rather than joined and
        hoped for: this process can read the whole disk, and a path like
        ``..%2f..%2fcards.db`` must not resolve.
        """
        _require("GET")
        if not SAFE_NAME.match(filename) or not filename.lower().endswith(".pdf"):
            _fail(404, "no such export")
        path = (EXPORT_DIR / filename).resolve()
        if path.parent != EXPORT_DIR.resolve() or not path.is_file():
            _fail(404, "no such export")
        return _serve_bytes(path.read_bytes(), "application/pdf", filename)
