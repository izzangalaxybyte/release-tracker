"""Release sources.

Every source exposes ``fetch(source_id, now, after_seq) -> Snapshot``:

* ``after_seq is None``: baseline request; ``released`` holds only the latest release.
* otherwise: ``released`` holds every release with ``seq > after_seq`` (oldest first,
  capped at 50), and is empty when nothing is new.

Only releases at or before ``now`` count as released.

Each also exposes ``search(query, limit) -> list[SearchResult]``.
"""

from . import anilist, mangadex, tvmaze

FETCHERS = {
    "anilist": anilist.fetch,
    "tvmaze": tvmaze.fetch,
    "mangadex": mangadex.fetch,
}

# search type (what the app calls it) -> search function
SEARCHERS = {
    "anime": anilist.search,
    "tv": tvmaze.search,
    "manga": mangadex.search,
}
