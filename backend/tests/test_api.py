import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3
import pytest
from moto import mock_aws

from tracker import api
from tracker.http import HttpError
from tracker.models import Release, SearchResult, Snapshot, Upcoming, WatchItem
from tracker.store import Store

NOW = datetime(2026, 10, 26, 4, 0, tzinfo=timezone.utc)
TOKEN = "s3cret-token"
MANGA_ID = "a1c7c817-4e59-43b7-9365-09675a149a6f"


def fake_fetch(source_id, now, after_seq):
    if source_id == "404":
        raise HttpError(404, "https://example", "not found")
    days = int(source_id) % 7 + 1 if source_id.isdigit() else 1
    upcoming = Upcoming("Episode 11", NOW + timedelta(days=days)) if source_id != "3" else None
    return Snapshot(title=f"Show {source_id}", status="RELEASING", url=None, image=None,
                    released=[Release("ep#00010", Decimal(10), "Episode 10", NOW)], upcoming=upcoming)


def fake_search(query, limit):
    return [SearchResult("anilist", "21", "ONE PIECE", 1999, "RELEASING", None, None, "TV"),
            SearchResult("anilist", "22", "Other", 2001, "FINISHED", None, None, "TV")]


@pytest.fixture
def call():
    with mock_aws():
        table = boto3.resource("dynamodb", region_name="us-east-1").create_table(
            TableName="t",
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
        )
        store = Store(table=table)
        fetchers = {"anilist": fake_fetch, "tvmaze": fake_fetch, "mangadex": fake_fetch}

        def _call(route_key, *, token=TOKEN, query=None, path=None, body=None, expected_token=lambda: TOKEN):
            event = {"routeKey": route_key, "headers": {"authorization": f"Bearer {token}"} if token else {},
                     "queryStringParameters": query, "pathParameters": path,
                     "body": json.dumps(body) if body is not None else None}
            resp = api.handle(event, expected_token=expected_token, store=store, fetchers=fetchers,
                              searchers={"anime": fake_search}, now=NOW)
            return resp["statusCode"], json.loads(resp["body"]) if "body" in resp else None

        _call.store = store
        yield _call


def test_rejects_missing_or_wrong_token(call):
    assert call("GET /watchlist", token=None)[0] == 401
    assert call("GET /watchlist", token="wrong")[0] == 401
    assert call("GET /watchlist")[0] == 200


def test_unconfigured_token_is_503_not_open(call):
    assert call("GET /watchlist", expected_token=lambda: None)[0] == 503


def test_add_list_remove(call):
    status, body = call("POST /watchlist", body={"source": "anilist", "source_id": "21"})
    assert status == 201
    assert body["item"]["last"] == {"label": "Episode 10", "released_at": "2026-10-26T04:00:00Z"}
    assert body["item"]["kind"] == "anime"
    assert call("POST /watchlist", body={"source": "anilist", "source_id": "21"})[0] == 409

    assert [i["title"] for i in call("GET /watchlist")[1]["items"]] == ["Show 21"]
    assert call("DELETE /watchlist/{source}/{source_id}", path={"source": "anilist", "source_id": "21"}) == (204, None)
    assert call("DELETE /watchlist/{source}/{source_id}", path={"source": "anilist", "source_id": "21"})[0] == 404
    assert call("GET /watchlist")[1]["items"] == []


def test_add_validates_input_and_source(call):
    assert call("POST /watchlist", body={"source": "netflix", "source_id": "1"})[0] == 400
    assert call("POST /watchlist", body={"source": "anilist", "source_id": "abc"})[0] == 400
    assert call("POST /watchlist", body={"source": "mangadex", "source_id": "21"})[0] == 400
    assert call("POST /watchlist", body={"source": "mangadex", "source_id": MANGA_ID.upper()})[0] == 201
    assert call("POST /watchlist", body={"source": "tvmaze", "source_id": "404"})[0] == 404


def test_search_marks_watched_titles(call):
    call("POST /watchlist", body={"source": "anilist", "source_id": "21"})
    status, body = call("GET /search", query={"type": "anime", "q": "one piece"})
    assert status == 200
    assert [(i["source_id"], i["on_watchlist"]) for i in body["items"]] == [("21", True), ("22", False)]
    assert call("GET /search", query={"type": "books", "q": "x"})[0] == 400
    assert call("GET /search", query={"type": "anime", "q": "  "})[0] == 400


def test_upcoming_sorted_and_skips_titles_without_next(call):
    for sid in ("5", "3", "1"):  # next in 6 days, none, 2 days
        call("POST /watchlist", body={"source": "tvmaze", "source_id": sid})
    items = call("GET /upcoming")[1]["items"]
    assert [(i["source_id"], i["next"]["at"]) for i in items] == [("1", "2026-10-28T04:00:00Z"), ("5", "2026-11-01T04:00:00Z")]


def test_notifications_cursor(call):
    store = call.store
    item = WatchItem(source="anilist", source_id="21", title="ONE PIECE", added_at=NOW)
    for hours in (0, 12, 24):
        store.add_notification(item, "ONE PIECE", f"at +{hours}h", [Release("ep#1", Decimal(1), "Episode 1")], NOW + timedelta(hours=hours))

    # First launch: cursor = install time, so older rows never show.
    status, body = call("GET /notifications", query={"after": "2026-10-26T10:00:00Z"})
    assert [i["body"] for i in body["items"]] == ["at +12h", "at +24h"]
    assert body["cursor"] == "2026-10-27T04:00:00Z#anilist#21" and body["more"] is False

    body = call("GET /notifications", query={"after": body["cursor"]})[1]
    assert body["items"] == [] and body["cursor"] == "2026-10-27T04:00:00Z#anilist#21"

    paged = call("GET /notifications", query={"limit": "2"})[1]
    assert len(paged["items"]) == 2 and paged["more"] is True
