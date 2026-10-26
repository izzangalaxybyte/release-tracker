"""Notification delivery.

There is no push service: the checker writes one row per title into the DynamoDB
notification feed, and the Android app polls the API for rows newer than its cursor
shortly after each scheduled check, then shows them as local notifications.
"""

import logging
from datetime import datetime

from .models import Release, WatchItem
from .store import Store

log = logging.getLogger(__name__)


def format_message(item: WatchItem, releases: list[Release]) -> tuple[str, str]:
    """(title, body) for one notification covering all new releases of a title."""
    releases = sorted(releases, key=lambda r: r.seq)
    if len(releases) == 1:
        body = f"{releases[0].label} is out"
    elif len(releases) <= 3:
        body = ", ".join(r.label for r in releases) + " are out"
    else:
        body = f"{len(releases)} new: {releases[0].label} … {releases[-1].label}"
    return item.title, body


class FeedNotifier:
    def __init__(self, store: Store):
        self.store = store

    def send(self, item: WatchItem, releases: list[Release], now: datetime) -> None:
        title, body = format_message(item, releases)
        sk = self.store.add_notification(item, title, body, releases, now)
        log.info("NOTIFY %s: %s", title, body, extra={"ref": item.ref, "feed_key": sk, "releases": [r.key for r in releases]})
