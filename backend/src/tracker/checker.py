"""Compares every watchlist title against its source and notifies about new releases."""

import logging
from datetime import datetime

from . import sources
from .models import Snapshot, WatchItem, to_iso, utcnow
from .notify import FeedNotifier
from .store import FAILED, SENT, Store

log = logging.getLogger(__name__)


def apply_snapshot(item: WatchItem, snap: Snapshot, now: datetime) -> None:
    """Copy display fields, upcoming release and (if newer) the latest release into item."""
    item.title, item.status, item.url, item.image = snap.title, snap.status, snap.url, snap.image
    item.next_label = snap.upcoming.label if snap.upcoming else None
    item.next_release_at = snap.upcoming.at if snap.upcoming else None
    latest = snap.latest
    if latest is not None and (item.last_seq is None or latest.seq > item.last_seq):
        item.last_seq, item.last_key, item.last_label = latest.seq, latest.key, latest.label
        item.last_released_at = latest.released_at
    item.checked_at = now
    item.last_error = None


def check_item(item: WatchItem, store: Store, notifier, fetchers, now: datetime) -> int:
    """Check one title. Returns how many releases were notified."""
    baseline = item.last_seq is None
    snap = fetchers[item.source](item.source_id, now, item.last_seq)

    if baseline:
        apply_snapshot(item, snap, now)
        store.save_state(item)
        log.info("Baseline %s: %s", item.title, item.last_label or "nothing released yet", extra={"ref": item.ref})
        return 0

    new = [r for r in snap.released if r.seq > item.last_seq]
    candidates = store.retryable_releases(item) + new
    claimed = [r for r in candidates if store.claim_release(item, r, now)]
    skipped = len(new) - len([r for r in claimed if r in new])

    apply_snapshot(item, snap, now)
    if not store.save_state(item):
        log.info("Skipping %s: removed from watchlist during check", item.ref)
        return 0

    if skipped:
        log.info("Already notified %d release(s) of %s, not sending again", skipped, item.title, extra={"ref": item.ref})
    if not claimed:
        return 0

    for r in claimed:
        log.info("NEW %s: %s — %s", item.kind, item.title, r.label, extra={"ref": item.ref, "released_at": to_iso(r.released_at)})
    try:
        notifier.send(item, claimed, now)
    except Exception as e:
        log.exception("Notification failed for %s", item.title, extra={"ref": item.ref})
        for r in claimed:
            store.mark_release(item, r, FAILED, now, error=str(e))
        return 0
    for r in claimed:
        store.mark_release(item, r, SENT, now)
    return len(claimed)


def run(store: Store | None = None, notifier=None, fetchers=None, now: datetime | None = None) -> dict:
    store = store or Store()
    notifier = notifier or FeedNotifier(store)
    fetchers = fetchers or sources.FETCHERS
    now = now or utcnow()

    items = store.list_watchlist()
    notified, errors = 0, 0
    for item in items:
        try:
            notified += check_item(item, store, notifier, fetchers, now)
        except Exception as e:
            errors += 1
            log.exception("Check failed for %s", item.ref)
            item.last_error = f"{to_iso(now)}: {e}"[:500]
            store.save_state(item)

    summary = {"checked": len(items), "notified": notified, "errors": errors, "at": to_iso(now)}
    log.info("Check complete: %d titles, %d notified, %d errors", len(items), notified, errors, extra=summary)
    return summary
