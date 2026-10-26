"""Release sources.

Every source exposes ``fetch(source_id, now, after_seq) -> Snapshot``:

* ``after_seq is None``: baseline request; ``released`` holds only the latest release.
* otherwise: ``released`` holds every release with ``seq > after_seq`` (oldest first,
  capped at 50), and is empty when nothing is new.

Only releases at or before ``now`` count as released.
"""

from . import anilist, mangadex, tvmaze

FETCHERS = {
    "anilist": anilist.fetch,
    "tvmaze": tvmaze.fetch,
    "mangadex": mangadex.fetch,
}
