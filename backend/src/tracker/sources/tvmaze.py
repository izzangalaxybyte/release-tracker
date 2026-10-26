"""TVmaze REST API (TV). source_id is the TVmaze show ID, e.g. 32158 for FBI.

Episodes are ordered by airstamp; episodes sharing an airstamp (streaming drops) are
ordered by episode number. Data is CC BY-SA, see https://www.tvmaze.com/api.
"""

from datetime import datetime
from decimal import Decimal
from urllib.parse import urlencode

from ..http import request_json
from ..models import Release, SearchResult, Snapshot, Upcoming, from_iso

BASE = "https://api.tvmaze.com"
MAX_RELEASES = 50


def search(query: str, limit: int = 10) -> list[SearchResult]:
    results = []
    for row in request_json(f"{BASE}/search/shows?{urlencode({'q': query})}")[:limit]:
        show = row["show"]
        premiered = show.get("premiered")
        results.append(SearchResult(
            source="tvmaze",
            source_id=str(show["id"]),
            title=show["name"],
            year=int(premiered[:4]) if premiered else None,
            status=show.get("status"),
            image=(show.get("image") or {}).get("medium"),
            url=show.get("url"),
            detail=(show.get("network") or show.get("webChannel") or {}).get("name"),
        ))
    return results


def fetch(source_id: str, now: datetime, after_seq: Decimal | None) -> Snapshot:
    show_id = int(source_id)
    show = request_json(f"{BASE}/shows/{show_id}?embed%5B%5D=previousepisode&embed%5B%5D=nextepisode")
    embedded = show.get("_embedded") or {}

    prev = _release(embedded.get("previousepisode"))
    if prev is not None and prev.released_at > now:
        prev = None

    if after_seq is None:
        released = [prev] if prev else []
    elif prev is not None and prev.seq <= after_seq:
        released = []  # nothing new, so skip downloading the full episode list
    else:
        episodes = request_json(f"{BASE}/shows/{show_id}/episodes")
        candidates = (r for r in map(_release, episodes) if r and r.released_at <= now and r.seq > after_seq)
        released = sorted(candidates, key=lambda r: r.seq)[-MAX_RELEASES:]

    upcoming = None
    if (nxt := _release(embedded.get("nextepisode"))) is not None:
        upcoming = Upcoming(nxt.label, nxt.released_at)

    return Snapshot(
        title=show["name"],
        status=show.get("status"),
        url=show.get("url"),
        image=(show.get("image") or {}).get("medium"),
        released=released,
        upcoming=upcoming,
    )


def _release(ep: dict | None) -> Release | None:
    if not ep or not ep.get("airstamp"):
        return None
    aired_at = from_iso(ep["airstamp"])
    number = ep.get("number")
    if number is None:
        label = f"Special · {ep['name']}"
    else:
        label = f"S{ep['season']:02d}E{number:02d} · {ep['name']}"
    return Release(
        key=f"tv#{ep['id']}",
        seq=Decimal(int(aired_at.timestamp())) + Decimal(number or 0) / 10000,
        label=label,
        released_at=aired_at,
        url=ep.get("url"),
    )
