"""The local overview server.  Localhost, one user, no auth -- see PROJECT.md.

Ports are not incidental here.  **8775 is the author's**, started from
``serve.bat``; **8776 is a throwaway** Claude may start for testing and must
stop in the same turn.  The split exists so that stopping one can never take
the other down, and the numbers differ from the sibling ``CardGenerator``
project's 8765/8766 so two galleries can run side by side.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import cherrypy

from .. import __version__
from ..export.formats import as_dicts as output_formats
from ..spec import as_dict
from ..store import DEFAULT_DB_PATH, database_url, make_engine
from .api import BacksApi, CardsApi, ExportApi, TagsApi, json_error

#: Repo root: this file is src/dixitgen/web/app.py, so three parents up.
ROOT = Path(__file__).resolve().parents[3]
STATIC = ROOT / "web"

DEFAULT_PORT = 8775

#: Uploads are photographs and AI renders, routinely 10-30 MB each, and a drop
#: of a whole deck arrives as one request.  CherryPy's default cap is 100 MB,
#: which a 40-card drop passes silently -- until it doesn't, with a 413 that
#: says nothing useful.
MAX_UPLOAD_BYTES = 512 * 1024 * 1024


class Api:
    """The JSON API.  ``/api/meta`` is the frontend's only source of numbers."""

    def __init__(self, engine, db_url: str):
        self.cards = CardsApi(engine)
        self.backs = BacksApi(engine)
        self.tags = TagsApi(engine)
        self.export = ExportApi(engine)
        self._db_url = db_url

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def meta(self) -> dict:
        payload = as_dict()
        payload["version"] = __version__
        # The export dialog's format menu, labels and figures included, so the
        # browser renders it without typing a measurement of its own.  A format
        # added in dixitgen.export.formats appears here with no frontend edit.
        payload["formats"] = output_formats()
        # Whether this server is serving the author's real library.  A check
        # that uploads and deletes cards uses this to refuse to run against
        # it -- the database holds the only copy of every image, and a test
        # run that wiped a deck would be unrecoverable.  A boolean, not the
        # path: the guard needs no filesystem detail.
        payload["is_default_library"] = self._db_url == _default_library_url()
        return payload


def _default_library_url() -> str:
    return "sqlite:///{}".format(DEFAULT_DB_PATH.as_posix())


class Root:
    def __init__(self, engine, db_url: str):
        self.api = Api(engine, db_url)

    @cherrypy.expose
    def index(self) -> None:
        raise cherrypy.HTTPRedirect("/web/index.html")


def serve(
    port: int = DEFAULT_PORT,
    host: str = "127.0.0.1",
    db_url: Optional[str] = None,
) -> None:
    """Run the overview in the foreground until Ctrl+C."""
    resolved = database_url(db_url)
    engine = make_engine(resolved)

    cherrypy.config.update(
        {
            "server.socket_host": host,
            "server.socket_port": port,
            "server.max_request_body_size": MAX_UPLOAD_BYTES,
            "engine.autoreload.on": False,
            "log.screen": True,
        }
    )
    config = {
        "/": {
            # Every failure reaches the browser as JSON it can display.
            "error_page.default": json_error,
            # No trailing-slash redirects.
            #
            # CherryPy answers `/api/export` with a 301 to `/api/export/`, and
            # a browser replays a redirected POST as a GET -- so every export
            # from the UI arrived as `GET /api/export/` and was refused 405,
            # while the same call through curl worked. Caught by
            # tests/check_gallery.py, which is exactly the class of bug the
            # verify gate cannot see.
            "tools.trailing_slash.on": False,
        },
        "/web": {
            "tools.staticdir.on": True,
            "tools.staticdir.dir": str(STATIC),
        },
    }
    cherrypy.quickstart(Root(engine, resolved), "/", config)
