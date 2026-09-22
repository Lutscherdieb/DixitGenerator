"""The card library: images, backs, tags and notes in one SQLite file.

`data/cards.db` holds the image bytes themselves, so it is the whole library --
and, since deletion here is permanent, the file to back up.
"""

from .db import DB_URL_ENV, DEFAULT_DB_PATH, database_url, make_engine, session_scope
from .models import Back, Base, Card, Tag
from .repo import (
    StoreError,
    add_back,
    add_card,
    batch_for_export,
    delete_back,
    delete_card,
    find_by_content,
    get_back,
    get_card,
    list_backs,
    list_cards,
    normalise_tag,
    prune_unused_tags,
    replace_image,
    set_focus,
    set_tags,
    to_back_image,
    to_card_art,
    all_tags,
    update_card,
)

__all__ = [
    "DB_URL_ENV",
    "DEFAULT_DB_PATH",
    "database_url",
    "make_engine",
    "session_scope",
    "Base",
    "Card",
    "Back",
    "Tag",
    "StoreError",
    "add_card",
    "add_back",
    "get_card",
    "get_back",
    "list_cards",
    "list_backs",
    "update_card",
    "set_focus",
    "set_tags",
    "all_tags",
    "prune_unused_tags",
    "replace_image",
    "delete_card",
    "delete_back",
    "find_by_content",
    "normalise_tag",
    "to_card_art",
    "to_back_image",
    "batch_for_export",
]
