from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3
import pytest
from moto import mock_aws

from tracker import checker
from tracker.models import Release, Snapshot, Upcoming, WatchItem
from tracker.notify import FeedNotifier
from tracker.store import FAILED, SENT, Store

NOW = datetime(2026, 10, 26, 4, 0, tzinfo=timezone.utc)


def ep(n: int) -> Release:
    return Release(key=f"ep#{n:05d}", seq=Decimal(n), label=f"Episode {n}", released_at=NOW - timedelta(days=100 - n))


class FakeSource:
    """Pretends to be a source whose latest released episode is self.latest."""

    def __init__(self, latest: int):
        self.latest = latest
        self.fail = False

    def __call__(self, source_id, now, after_seq):
        if self.fail:
            raise RuntimeError("source down")
        if after_seq is None:
            released = [ep(self.latest)]
        else:
            released = [ep(n) for n in range(int(after_seq) + 1, self.latest + 1)]
        return Snapshot(title="Show", status="RELEASING", url=None, image=None, released=released,
                        upcoming=Upcoming(f"Episode {self.latest + 1}", NOW + timedelta(days=7)))


class RecordingNotifier:
    def __init__(self):
        self.sent: list[list[str]] = []
        self.fail = False

    def send(self, item, releases, now):
        if self.fail:
            raise RuntimeError("push down")
        self.sent.append([r.key for r in releases])


@pytest.fixture
def env():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.create_table(
            TableName="t",
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
        )
        store = Store(table=table)
        store.add(WatchItem(source="anilist", source_id="21", title="Show", added_at=NOW))
        source, notifier = FakeSource(latest=10), RecordingNotifier()

        def run(now=NOW):
            return checker.run(store=store, notifier=notifier, fetchers={"anilist": source}, now=now)

        yield store, source, notifier, run


def statuses(store):
    item = store.get("anilist", "21")
    return {row["sk"]: row["status"] for row in store.release_log(item)}


def test_first_check_sets_baseline_without_notifying(env):
    store, _, notifier, run = env
    assert run()["notified"] == 0
    item = store.get("anilist", "21")
    assert item.last_seq == 10 and item.last_label == "Episode 10"
    assert item.next_label == "Episode 11"
    assert notifier.sent == []


def test_new_release_is_notified_exactly_once(env):
    store, source, notifier, run = env
    run()
    source.latest = 12
    assert run()["notified"] == 2
    assert run()["notified"] == 0
    assert notifier.sent == [["ep#00011", "ep#00012"]]
    assert statuses(store) == {"ep#00011": SENT, "ep#00012": SENT}
    assert store.get("anilist", "21").last_seq == 12


def test_rewound_state_does_not_renotify(env):
    store, source, notifier, run = env
    run()
    source.latest = 11
    run()
    item = store.get("anilist", "21")
    item.last_seq = Decimal(10)  # e.g. a lost state write, or two overlapping runs
    store.save_state(item)
    assert run()["notified"] == 0
    assert notifier.sent == [["ep#00011"]]


def test_failed_send_is_retried_then_stops(env):
    store, source, notifier, run = env
    run()
    source.latest = 11
    notifier.fail = True
    run()
    assert statuses(store) == {"ep#00011": FAILED}
    notifier.fail = False
    assert run()["notified"] == 1
    assert run()["notified"] == 0
    assert notifier.sent == [["ep#00011"]]


def test_source_error_is_recorded_and_others_continue(env):
    store, source, notifier, run = env
    store.add(WatchItem(source="tvmaze", source_id="1", title="Other", added_at=NOW))
    fetchers = {"anilist": source, "tvmaze": FakeSource(latest=3)}
    source.fail = True
    summary = checker.run(store=store, notifier=notifier, fetchers=fetchers, now=NOW)
    assert summary == {"checked": 2, "notified": 0, "errors": 1, "at": "2026-10-26T04:00:00Z"}
    assert "source down" in store.get("anilist", "21").last_error
    assert store.get("tvmaze", "1").last_seq == 3


def test_removed_title_is_not_resurrected(env):
    store, source, notifier, run = env
    item = store.list_watchlist()[0]
    store.remove("anilist", "21")
    assert store.save_state(item) is False
    assert store.list_watchlist() == []


def test_feed_gets_one_row_per_title_and_cursor_pages(env):
    store, source, _, _ = env
    feed = FeedNotifier(store)

    def run(now):
        return checker.run(store=store, notifier=feed, fetchers={"anilist": source}, now=now)

    run(NOW)
    source.latest = 12
    run(NOW + timedelta(hours=12))
    rows = store.list_notifications()
    assert [(r["title"], r["body"]) for r in rows] == [("Show", "Episode 11, Episode 12 are out")]
    assert rows[0]["sk"] == "2026-10-26T16:00:00Z#anilist#21"
    assert rows[0]["expires_at"] > int(NOW.timestamp())

    cursor = rows[-1]["sk"]
    run(NOW + timedelta(hours=24))
    assert store.list_notifications(after=cursor) == []
    source.latest = 13
    run(NOW + timedelta(hours=36))
    assert [r["body"] for r in store.list_notifications(after=cursor)] == ["Episode 13 is out"]
