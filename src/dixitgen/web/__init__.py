"""The local overview: a JSON API and the static browser client in ``web/``."""

from .app import DEFAULT_PORT, serve

__all__ = ["serve", "DEFAULT_PORT"]
