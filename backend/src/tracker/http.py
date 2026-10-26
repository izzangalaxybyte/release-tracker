"""Minimal JSON-over-HTTP client. Stdlib only, so the Lambda bundle has no dependencies."""

import json
import logging
import time
import urllib.error
import urllib.request

USER_AGENT = "release-tracker/0.1 (+https://github.com/izzangalaxybyte/release-tracker)"
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_RETRY_DELAY = 30

log = logging.getLogger(__name__)


class HttpError(Exception):
    def __init__(self, status: int, url: str, body: str):
        super().__init__(f"HTTP {status} for {url}: {body[:300]}")
        self.status = status


def request_json(url, *, method="GET", body=None, headers=None, timeout=15, retries=3):
    data = json.dumps(body).encode() if body is not None else None
    all_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if data is not None:
        all_headers["Content-Type"] = "application/json"
    all_headers.update(headers or {})

    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, method=method, headers=all_headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="replace")
            if e.code not in RETRY_STATUSES or attempt == retries:
                raise HttpError(e.code, url, text) from None
            delay = _retry_delay(e.headers.get("Retry-After"), attempt)
            log.warning("HTTP %s, retrying in %ss", e.code, delay, extra={"url": url})
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries:
                raise
            delay = 2**attempt
        time.sleep(delay)


def _retry_delay(retry_after, attempt):
    try:
        return min(int(retry_after), MAX_RETRY_DELAY)
    except (TypeError, ValueError):
        return min(2**attempt, MAX_RETRY_DELAY)
