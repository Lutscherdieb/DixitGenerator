"""Engine and session handling for the card database.

The database is a **single file** holding the card images themselves, not
paths to them.  That makes `data/cards.db` the whole library: copy it and you
have copied the deck.

It also makes it the **only** copy.  Deletion here is permanent (the author's
choice, 2026-09-22), so `data/cards.db` is the file to back up before a big
tidy-up.

``DIXIT_DB_URL`` overrides the default, which is how a check runs against a
scratch database instead of the author's library -- the same shape as
``DIXIT_URL`` for the server.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

#: Repo root: this file is src/dixitgen/store/db.py, so three parents up.
ROOT = Path(__file__).resolve().parents[3]

DEFAULT_DB_PATH = ROOT / "data" / "cards.db"

#: Environment override, for scratch databases in checks.
DB_URL_ENV = "DIXIT_DB_URL"


def database_url(explicit: Optional[str] = None) -> str:
    """The URL to open, in precedence order: argument, environment, default."""
    if explicit:
        return explicit
    from_env = os.environ.get(DB_URL_ENV)
    if from_env:
        return from_env
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return "sqlite:///{}".format(DEFAULT_DB_PATH.as_posix())


def make_engine(url: Optional[str] = None, echo: bool = False) -> Engine:
    """An engine with the schema already created."""
    engine = create_engine(database_url(url), echo=echo, future=True)
    Base.metadata.create_all(engine)
    return engine


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """A transaction that commits on success and rolls back on any exception.

    Rolling back matters more than usual here: a half-written card is a row
    with image bytes but no thumbnail, which the overview then renders as a
    broken tile forever.
    """
    session = make_session_factory(engine)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
