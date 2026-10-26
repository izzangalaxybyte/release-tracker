"""MangaDex API (manga). source_id is the MangaDex manga UUID.

Chapters are matched by chapter *number*, not upload ID: several groups (or an official
MANGA Plus link plus fan scanlations) often upload the same chapter, and an old chapter
can be re-uploaded long after newer ones. The earliest upload of a number is kept.
MangaDex has no release schedule, so manga never have an upcoming release.
"""

import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from ..http import request_json
from ..models import Release, Snapshot, from_iso

BASE = "https://api.mangadex.org"
MAX_RELEASES = 50
CONTENT_RATINGS = ["safe", "suggestive", "erotica", "pornographic"]


def languages() -> list[str]:
    return [code.strip() for code in os.environ.get("MANGA_LANGUAGES", "en").split(",") if code.strip()]


def fetch(source_id: str, now: datetime, after_seq: Decimal | None) -> Snapshot:
    manga = request_json(f"{BASE}/manga/{source_id}?includes%5B%5D=cover_art")["data"]
    params = [("translatedLanguage[]", code) for code in languages()]
    params += [("contentRating[]", rating) for rating in CONTENT_RATINGS]
    params += [("order[readableAt]", "desc"), ("limit", "100"), ("includeExternalUrl", "1"), ("includeFuturePublishAt", "0")]
    feed = request_json(f"{BASE}/manga/{source_id}/feed?{urlencode(params)}")

    by_number: dict[Decimal, Release] = {}
    for chapter in feed["data"]:
        attrs = chapter["attributes"]
        number = _chapter_number(attrs.get("chapter"))
        readable_at = from_iso(attrs.get("readableAt"))
        if number is None or readable_at is None or readable_at > now:
            continue
        current = by_number.get(number)
        if current is None or readable_at < current.released_at:
            text = format(number.normalize(), "f")
            by_number[number] = Release(
                key=f"ch#{text}",
                seq=number,
                label=f"Chapter {text}",
                released_at=readable_at,
                url=attrs.get("externalUrl") or f"https://mangadex.org/chapter/{chapter['id']}",
            )

    released = sorted(by_number.values(), key=lambda r: r.seq)
    if after_seq is None:
        released = released[-1:]
    else:
        released = [r for r in released if r.seq > after_seq][-MAX_RELEASES:]

    attrs = manga["attributes"]
    return Snapshot(
        title=_title(attrs),
        status=attrs.get("status"),
        url=f"https://mangadex.org/title/{source_id}",
        image=_cover_url(source_id, manga.get("relationships", [])),
        released=released,
    )


def _chapter_number(value: str | None) -> Decimal | None:
    try:
        number = Decimal(value)
    except (TypeError, InvalidOperation):
        return None
    return number if number.is_finite() else None


def _title(attrs: dict) -> str:
    titles = attrs.get("title") or {}
    if "en" in titles:
        return titles["en"]
    for alt in attrs.get("altTitles") or []:
        if "en" in alt:
            return alt["en"]
    return next(iter(titles.values()), "Unknown title")


def _cover_url(manga_id: str, relationships: list[dict]) -> str | None:
    for rel in relationships:
        if rel["type"] == "cover_art" and (file_name := (rel.get("attributes") or {}).get("fileName")):
            return f"https://uploads.mangadex.org/covers/{manga_id}/{file_name}.256.jpg"
    return None
