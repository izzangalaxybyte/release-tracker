"""Watchlist operations shared by the API and the CLI."""

import re
from datetime import datetime

from .checker import apply_snapshot
from .models import SOURCES, WatchItem
from .store import Store

_ID_PATTERNS = {
    "anilist": re.compile(r"\d{1,10}"),
    "tvmaze": re.compile(r"\d{1,10}"),
    "mangadex": re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"),
}


def validate_ref(source, source_id) -> str:
    """Return the normalized source_id, or raise ValueError."""
    if source not in SOURCES:
        raise ValueError(f"source must be one of {', '.join(SOURCES)}")
    source_id = str(source_id or "").strip().lower()
    if not _ID_PATTERNS[source].fullmatch(source_id):
        raise ValueError(f"invalid {source} id")
    return source_id


def add_title(store: Store, source: str, source_id: str, fetchers, now: datetime) -> tuple[WatchItem, bool]:
    """Add a title with its current latest release as the baseline (so nothing old notifies).

    Returns (item, created); created is False if it was already on the watchlist.
    """
    if existing := store.get(source, source_id):
        return existing, False
    snap = fetchers[source](source_id, now, None)
    item = WatchItem(source=source, source_id=source_id, title=snap.title, added_at=now)
    apply_snapshot(item, snap, now)
    if store.add(item):
        return item, True
    return store.get(source, source_id), False
