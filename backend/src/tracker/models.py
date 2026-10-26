from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

# source -> kind of media it tracks
SOURCES = {"anilist": "anime", "tvmaze": "tv", "mangadex": "manga"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def from_iso(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value).astimezone(timezone.utc) if value else None


@dataclass(frozen=True)
class Release:
    """One episode or chapter as reported by a source."""

    key: str  # stable within a title: "ep#01180", "ch#1196", "tv#3245161"
    seq: Decimal  # monotonic order: episode/chapter number, or airstamp for TV
    label: str  # "Episode 1180", "Chapter 1196", "S09E04 · Title"
    released_at: datetime | None = None
    url: str | None = None


@dataclass(frozen=True)
class Upcoming:
    label: str
    at: datetime


@dataclass
class Snapshot:
    """What a source says about a title right now."""

    title: str
    status: str | None
    url: str | None
    image: str | None
    released: list[Release] = field(default_factory=list)  # ascending by seq
    upcoming: Upcoming | None = None

    @property
    def latest(self) -> Release | None:
        return self.released[-1] if self.released else None


@dataclass(frozen=True)
class SearchResult:
    source: str
    source_id: str
    title: str
    year: int | None
    status: str | None
    image: str | None
    url: str | None
    detail: str | None = None  # anime format, TV network, or manga demographic


@dataclass
class WatchItem:
    """A watchlist entry plus the last-seen state the checker compares against."""

    source: str
    source_id: str
    title: str
    added_at: datetime
    status: str | None = None
    url: str | None = None
    image: str | None = None
    last_seq: Decimal | None = None  # None until the first check sets a baseline
    last_key: str | None = None
    last_label: str | None = None
    last_released_at: datetime | None = None
    next_label: str | None = None
    next_release_at: datetime | None = None
    checked_at: datetime | None = None
    last_error: str | None = None

    @property
    def kind(self) -> str:
        return SOURCES[self.source]

    @property
    def ref(self) -> str:
        return f"{self.source}#{self.source_id}"
