"""The local overview server.  Localhost, one user, no auth -- see PROJECT.md.

Ports are not incidental here.  **8775 is the author's**, started from
``serve.bat``; **8776 is a throwaway** Claude may start for testing and must
stop in the same turn.  The split exists so that stopping one can never take
the other down, and the numbers differ from the sibling ``CardGenerator``
project's 8765/8766 so two galleries can run side by side.
"""

from __future__ import annotations

from pathlib import Path

import cherrypy

from .. import __version__
from ..spec import as_dict

#: Repo root: this file is src/dixitgen/web/app.py, so three parents up.
ROOT = Path(__file__).resolve().parents[3]
STATIC = ROOT / "web"

DEFAULT_PORT = 8775


class Api:
    """The JSON the browser overview reads.

    ``/api/meta`` is deliberately the first endpoint: the frontend must take
    every measurement from here rather than typing one of its own, which is
    what ``tools/check_geometry_literals.py`` enforces over ``web/``.
    """

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def meta(self) -> dict:
        payload = as_dict()
        payload["version"] = __version__
        return payload


class Root:
    api = Api()

    @cherrypy.expose
    def index(self) -> None:
        raise cherrypy.HTTPRedirect("/web/index.html")


def serve(port: int = DEFAULT_PORT, host: str = "127.0.0.1") -> None:
    """Run the overview in the foreground until Ctrl+C."""
    cherrypy.config.update(
        {
            "server.socket_host": host,
            "server.socket_port": port,
            "engine.autoreload.on": False,
            "log.screen": True,
        }
    )
    config = {
        "/web": {
            "tools.staticdir.on": True,
            "tools.staticdir.dir": str(STATIC),
        }
    }
    cherrypy.quickstart(Root(), "/", config)
