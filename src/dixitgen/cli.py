"""Command line entry point.  ``serve.bat`` calls this; so can you."""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="dixitgen", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    from .web.app import DEFAULT_PORT

    serve_cmd = sub.add_parser("serve", help="run the local overview")
    serve_cmd.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="8775 is the author's; a throwaway server belongs on 8776 "
        "(default: %(default)s)",
    )
    serve_cmd.add_argument("--host", default="127.0.0.1")

    args = parser.parse_args(argv)
    if args.command == "serve":
        from .web.app import serve

        serve(port=args.port, host=args.host)
        return 0

    parser.error("unknown command {!r}".format(args.command))
    return 2


if __name__ == "__main__":
    sys.exit(main())
