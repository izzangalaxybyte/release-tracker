"""AniList GraphQL (anime). source_id is the AniList media ID, e.g. 21 for One Piece.

An episode counts as released at its Japanese broadcast time (AiringSchedule.airingAt).
"""

from datetime import datetime, timezone
from decimal import Decimal

from ..http import HttpError, request_json
from ..models import Release, SearchResult, Snapshot, Upcoming

URL = "https://graphql.anilist.co"
MAX_RELEASES = 50

QUERY = """
query ($id: Int, $now: Int, $after: Int, $perPage: Int) {
  Media(id: $id, type: ANIME) {
    title { romaji english }
    status
    episodes
    siteUrl
    coverImage { large }
    nextAiringEpisode { episode airingAt }
  }
  Page(perPage: $perPage) {
    airingSchedules(mediaId: $id, airingAt_lesser: $now, episode_greater: $after, sort: EPISODE_DESC) {
      episode
      airingAt
    }
  }
}
"""


SEARCH_QUERY = """
query ($q: String, $perPage: Int) {
  Page(perPage: $perPage) {
    media(search: $q, type: ANIME, isAdult: false, sort: SEARCH_MATCH) {
      id
      title { romaji english }
      status
      format
      seasonYear
      startDate { year }
      siteUrl
      coverImage { medium }
    }
  }
}
"""


def search(query: str, limit: int = 10) -> list[SearchResult]:
    data = request_json(URL, method="POST", body={"query": SEARCH_QUERY, "variables": {"q": query, "perPage": limit}})
    if data.get("errors"):
        raise HttpError(200, URL, str(data["errors"]))
    return [
        SearchResult(
            source="anilist",
            source_id=str(m["id"]),
            title=m["title"].get("english") or m["title"]["romaji"],
            year=m.get("seasonYear") or (m.get("startDate") or {}).get("year"),
            status=m.get("status"),
            image=(m.get("coverImage") or {}).get("medium"),
            url=m.get("siteUrl"),
            detail=m.get("format"),
        )
        for m in data["data"]["Page"]["media"]
    ]


def fetch(source_id: str, now: datetime, after_seq: Decimal | None) -> Snapshot:
    variables = {
        "id": int(source_id),
        "now": int(now.timestamp()) + 1,  # airingAt_lesser is exclusive
        "after": int(after_seq) if after_seq is not None else 0,
        "perPage": 1 if after_seq is None else MAX_RELEASES,
    }
    data = request_json(URL, method="POST", body={"query": QUERY, "variables": variables})
    if data.get("errors"):
        raise HttpError(200, URL, str(data["errors"]))
    media = data["data"]["Media"]
    site_url = media.get("siteUrl")

    released = [
        _release(row["episode"], datetime.fromtimestamp(row["airingAt"], timezone.utc), site_url)
        for row in reversed(data["data"]["Page"]["airingSchedules"])
    ]
    # Old finished shows often have no airing schedule; fall back to the episode count.
    if not released and after_seq is None and media["status"] == "FINISHED" and media.get("episodes"):
        released = [_release(media["episodes"], None, site_url)]

    upcoming = None
    if nxt := media.get("nextAiringEpisode"):
        upcoming = Upcoming(f"Episode {nxt['episode']}", datetime.fromtimestamp(nxt["airingAt"], timezone.utc))

    title = media["title"]
    return Snapshot(
        title=title.get("english") or title["romaji"],
        status=media["status"],
        url=site_url,
        image=(media.get("coverImage") or {}).get("large"),
        released=released,
        upcoming=upcoming,
    )


HISTORY_QUERY = """
query ($id: Int, $since: Int, $now: Int, $page: Int) {
  Page(page: $page, perPage: 50) {
    pageInfo { hasNextPage }
    airingSchedules(mediaId: $id, airingAt_greater: $since, airingAt_lesser: $now, sort: TIME_DESC) {
      episode
      airingAt
    }
  }
}
"""
HISTORY_MAX_PAGES = 10


def history(source_id: str, since: datetime, now: datetime) -> list[Release]:
    """Episodes that aired (in Japan) between since and now, newest first."""
    url = f"https://anilist.co/anime/{int(source_id)}"
    variables = {"id": int(source_id), "since": int(since.timestamp()) - 1, "now": int(now.timestamp()) + 1}
    releases = []
    for page in range(1, HISTORY_MAX_PAGES + 1):
        data = request_json(URL, method="POST", body={"query": HISTORY_QUERY, "variables": {**variables, "page": page}})
        if data.get("errors"):
            raise HttpError(200, URL, str(data["errors"]))
        result = data["data"]["Page"]
        releases += [_release(r["episode"], datetime.fromtimestamp(r["airingAt"], timezone.utc), url)
                     for r in result["airingSchedules"]]
        if not result["pageInfo"]["hasNextPage"]:
            break
    return releases


def _release(episode: int, aired_at: datetime | None, url: str | None) -> Release:
    return Release(key=f"ep#{episode:05d}", seq=Decimal(episode), label=f"Episode {episode}", released_at=aired_at, url=url)
