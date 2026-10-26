"""AniList GraphQL (anime). source_id is the AniList media ID, e.g. 21 for One Piece.

An episode counts as released at its Japanese broadcast time (AiringSchedule.airingAt).
"""

from datetime import datetime, timezone
from decimal import Decimal

from ..http import HttpError, request_json
from ..models import Release, Snapshot, Upcoming

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


def _release(episode: int, aired_at: datetime | None, url: str | None) -> Release:
    return Release(key=f"ep#{episode:05d}", seq=Decimal(episode), label=f"Episode {episode}", released_at=aired_at, url=url)
