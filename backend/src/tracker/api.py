"""HTTP API routes (API Gateway HTTP API, payload format 2.0). Routes are declared in template.yaml.

Every request needs `Authorization: Bearer <token>`; the token lives in SSM Parameter Store.
"""

import base64
import hmac
import json
import logging
import urllib.error
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Callable

from .http import HttpError
from .models import Release, WatchItem, to_iso
from .store import Store
from .watchlist import add_title, validate_ref

log = logging.getLogger(__name__)

SEARCH_LIMIT = 10
MAX_QUERY_LENGTH = 100
MAX_NOTIFICATIONS = 100
DEFAULT_HISTORY_DAYS = 365
MAX_HISTORY_DAYS = 730
UPSTREAM_ERRORS = (HttpError, urllib.error.URLError, TimeoutError)


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class Deps:
    store: Store
    fetchers: dict
    searchers: dict
    histories: dict
    now: datetime


class Request:
    def __init__(self, event: dict):
        self.query = event.get("queryStringParameters") or {}
        self.path = event.get("pathParameters") or {}
        self._event = event

    def json(self) -> dict:
        raw = self._event.get("body") or ""
        if self._event.get("isBase64Encoded"):
            raw = base64.b64decode(raw).decode()
        try:
            body = json.loads(raw or "{}")
        except json.JSONDecodeError:
            raise ApiError(400, "body must be JSON") from None
        if not isinstance(body, dict):
            raise ApiError(400, "body must be a JSON object")
        return body


# --- routes ------------------------------------------------------------------------------


def list_watchlist(req: Request, deps: Deps):
    items = sorted(deps.store.list_watchlist(), key=lambda i: i.title.lower())
    return 200, {"items": [item_json(i) for i in items]}


def add_to_watchlist(req: Request, deps: Deps):
    body = req.json()
    source = body.get("source")
    source_id = _valid_ref(source, body.get("source_id"))
    try:
        item, created = add_title(deps.store, source, source_id, deps.fetchers, deps.now)
    except HttpError as e:
        if e.status in (400, 404):
            raise ApiError(404, f"{source} has no title {source_id}") from None
        raise ApiError(502, f"{source} is unavailable") from None
    except UPSTREAM_ERRORS:
        raise ApiError(502, f"{source} is unavailable") from None
    return (201 if created else 409), {"item": item_json(item)}


def remove_from_watchlist(req: Request, deps: Deps):
    source = req.path.get("source")
    source_id = _valid_ref(source, req.path.get("source_id"))
    if deps.store.get(source, source_id) is None:
        raise ApiError(404, "not on the watchlist")
    deps.store.remove(source, source_id)
    return 204, None


def search(req: Request, deps: Deps):
    kind = req.query.get("type")
    query = (req.query.get("q") or "").strip()
    if kind not in deps.searchers:
        raise ApiError(400, f"type must be one of {', '.join(deps.searchers)}")
    if not 1 <= len(query) <= MAX_QUERY_LENGTH:
        raise ApiError(400, f"q must be 1-{MAX_QUERY_LENGTH} characters")
    try:
        results = deps.searchers[kind](query, SEARCH_LIMIT)
    except UPSTREAM_ERRORS:
        log.exception("Search failed")
        raise ApiError(502, "search source is unavailable") from None
    watched = {item.ref for item in deps.store.list_watchlist()}
    return 200, {"items": [
        {**asdict(r), "kind": kind, "on_watchlist": f"{r.source}#{r.source_id}" in watched} for r in results
    ]}


def upcoming(req: Request, deps: Deps):
    items = sorted((i for i in deps.store.list_watchlist() if i.next_release_at), key=lambda i: i.next_release_at)
    return 200, {"items": [item_json(i) for i in items]}


def release_history(req: Request, deps: Deps):
    """Every release of a title in the last `days` (default 365), newest first, plus the next one if known."""
    source = req.path.get("source")
    source_id = _valid_ref(source, req.path.get("source_id"))
    try:
        days = min(max(int(req.query.get("days", DEFAULT_HISTORY_DAYS)), 1), MAX_HISTORY_DAYS)
    except ValueError:
        raise ApiError(400, "days must be a number") from None
    since = deps.now - timedelta(days=days)
    try:
        releases = deps.histories[source](source_id, since, deps.now)
    except HttpError as e:
        if e.status in (400, 404):
            raise ApiError(404, f"{source} has no title {source_id}") from None
        raise ApiError(502, f"{source} is unavailable") from None
    except UPSTREAM_ERRORS:
        raise ApiError(502, f"{source} is unavailable") from None
    item = deps.store.get(source, source_id)
    return 200, {
        "source": source,
        "source_id": source_id,
        "since": to_iso(since),
        "items": [release_json(r) for r in releases],
        "next": {"label": item.next_label, "at": to_iso(item.next_release_at)} if item and item.next_label else None,
    }


def notifications(req: Request, deps: Deps):
    """Feed the app polls. `after` is a cursor: the `cursor` from the previous response, or an
    ISO-8601 UTC time (e.g. the install time) to skip everything older."""
    after = req.query.get("after") or None
    try:
        limit = min(max(int(req.query.get("limit", MAX_NOTIFICATIONS)), 1), MAX_NOTIFICATIONS)
    except ValueError:
        raise ApiError(400, "limit must be a number") from None
    rows = deps.store.list_notifications(after=after, limit=limit)
    return 200, {
        "items": [notification_json(r) for r in rows],
        "cursor": rows[-1]["sk"] if rows else after,
        "more": len(rows) == limit,
    }


ROUTES: dict[str, Callable] = {
    "GET /watchlist": list_watchlist,
    "POST /watchlist": add_to_watchlist,
    "DELETE /watchlist/{source}/{source_id}": remove_from_watchlist,
    "GET /search": search,
    "GET /upcoming": upcoming,
    "GET /notifications": notifications,
    "GET /releases/{source}/{source_id}": release_history,
}


# --- plumbing ----------------------------------------------------------------------------


def handle(event: dict, *, expected_token: Callable[[], str | None], **deps) -> dict:
    route_key = event.get("routeKey", "")
    try:
        _authorize(event, expected_token)
        route = ROUTES.get(route_key)
        if route is None:
            raise ApiError(404, "no such route")
        status, body = route(Request(event), Deps(**deps))
    except ApiError as e:
        status, body = e.status, {"error": e.message}
    except Exception:
        log.exception("Unhandled error on %s", route_key)
        status, body = 500, {"error": "internal error"}
    log.info("%s -> %s", route_key, status)
    return _response(status, body)


def _authorize(event: dict, expected_token: Callable[[], str | None]) -> None:
    token = expected_token()
    if not token:
        raise ApiError(503, "API token not configured; run scripts/write_app_config.py")
    presented = (event.get("headers") or {}).get("authorization", "")
    if not hmac.compare_digest(presented.encode(), f"Bearer {token}".encode()):
        raise ApiError(401, "unauthorized")


def _valid_ref(source, source_id) -> str:
    try:
        return validate_ref(source, source_id)
    except ValueError as e:
        raise ApiError(400, str(e)) from None


def item_json(item: WatchItem) -> dict:
    return {
        "source": item.source,
        "source_id": item.source_id,
        "kind": item.kind,
        "title": item.title,
        "status": item.status,
        "url": item.url,
        "image": item.image,
        "added_at": to_iso(item.added_at),
        "last": {"label": item.last_label, "released_at": to_iso(item.last_released_at)} if item.last_label else None,
        "next": {"label": item.next_label, "at": to_iso(item.next_release_at)} if item.next_label else None,
        "checked_at": to_iso(item.checked_at),
        "error": item.last_error,
    }


def release_json(release: Release) -> dict:
    return {"key": release.key, "label": release.label, "released_at": to_iso(release.released_at), "url": release.url}


def notification_json(row: dict) -> dict:
    return {
        "id": row["sk"],
        **{k: row.get(k) for k in ("title", "body", "kind", "source", "source_id", "url", "image", "created_at")},
        "releases": row.get("releases", []),
    }


def _json_default(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _response(status: int, body) -> dict:
    response = {"statusCode": status, "headers": {"content-type": "application/json"}}
    if body is not None:
        response["body"] = json.dumps(body, default=_json_default, ensure_ascii=False)
    return response
