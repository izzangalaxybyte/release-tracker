from datetime import datetime, timezone
from decimal import Decimal

from tracker.sources import mangadex, tvmaze

NOW = datetime(2026, 10, 26, 4, 0, tzinfo=timezone.utc)


def chapter(cid, number, readable_at, external=None):
    return {"id": cid, "attributes": {"chapter": number, "readableAt": readable_at, "externalUrl": external}}


def fake_mangadex(monkeypatch, chapters):
    def request_json(url, **_):
        if "/feed?" in url:
            return {"data": chapters}
        return {"data": {"attributes": {"title": {"ja-ro": "One Piece"}, "status": "ongoing"}, "relationships": []}}

    monkeypatch.setattr(mangadex, "request_json", request_json)


def test_mangadex_dedupes_by_number_and_ignores_reuploads(monkeypatch):
    fake_mangadex(monkeypatch, [
        chapter("c", "1196", "2026-10-18T15:10:58+00:00", "https://mangaplus.example/1196"),
        chapter("d", "1196", "2026-10-19T10:00:00+00:00"),  # second group, later: ignored
        chapter("e", "1195", "2026-10-11T15:10:30+00:00"),
        chapter("f", "4", "2026-08-26T17:30:11+00:00"),  # late re-upload of an old chapter
        chapter("g", None, "2026-10-20T00:00:00+00:00"),  # oneshot/extra without a number
        chapter("h", "1197", "2026-10-27T00:00:00+00:00"),  # not readable yet
    ])
    baseline = mangadex.fetch("x", NOW, None)
    assert [r.key for r in baseline.released] == ["ch#1196"]
    assert baseline.released[0].url == "https://mangaplus.example/1196"
    assert baseline.title == "One Piece"

    newer = mangadex.fetch("x", NOW, Decimal("1194"))
    assert [r.label for r in newer.released] == ["Chapter 1195", "Chapter 1196"]


def test_mangadex_decimal_chapters(monkeypatch):
    fake_mangadex(monkeypatch, [chapter("a", "10.5", "2026-10-01T00:00:00+00:00"), chapter("b", "10", "2026-09-01T00:00:00+00:00")])
    assert [r.key for r in mangadex.fetch("x", NOW, Decimal(10)).released] == ["ch#10.5"]


def episode(eid, season, number, airstamp, name="Ep"):
    return {"id": eid, "season": season, "number": number, "airstamp": airstamp, "name": name, "url": None}


def test_tvmaze_skips_episode_list_when_nothing_new(monkeypatch):
    calls = []

    def request_json(url, **_):
        calls.append(url)
        return {"name": "FBI", "status": "Running", "_embedded": {
            "previousepisode": episode(1, 9, 3, "2026-10-20T00:00:00+00:00"),
            "nextepisode": episode(2, 9, 4, "2026-10-27T00:00:00+00:00", "Next")}}

    monkeypatch.setattr(tvmaze, "request_json", request_json)
    base = tvmaze.fetch("32158", NOW, None)
    assert base.released[0].label == "S09E03 · Ep"
    assert base.upcoming.label == "S09E04 · Next"
    assert tvmaze.fetch("32158", NOW, base.released[0].seq).released == []
    assert len(calls) == 2  # no /episodes download


def test_tvmaze_streaming_drop_orders_by_episode_number(monkeypatch):
    drop = "2026-10-25T07:00:00+00:00"
    episodes = [episode(10 + n, 2, n, drop) for n in (3, 1, 2)] + [episode(1, 1, 8, "2025-01-01T07:00:00+00:00")]

    def request_json(url, **_):
        if url.endswith("/episodes"):
            return episodes
        return {"name": "S", "_embedded": {"previousepisode": episodes[0]}}

    monkeypatch.setattr(tvmaze, "request_json", request_json)
    after = tvmaze._release(episodes[3]).seq
    assert [r.label[:6] for r in tvmaze.fetch("1", NOW, after).released] == ["S02E01", "S02E02", "S02E03"]
