#!/usr/bin/env python3
"""Manage the watchlist directly in DynamoDB (until the API exists, and for testing).

  python scripts/watchlist.py add anilist 21
  python scripts/watchlist.py list
  python scripts/watchlist.py rewind anilist 21 --by 2 [--forget]
  python scripts/watchlist.py remove anilist 21
  python scripts/watchlist.py notifications [--after <sort key>]
  python scripts/watchlist.py peek mangadex <uuid>      # query the source only, no AWS

Uses AWS_PROFILE (default "release-tracker") and finds the table from the stack outputs.
"""

import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend" / "src"))

import boto3  # noqa: E402

from tracker import sources  # noqa: E402
from tracker.models import SOURCES, WatchItem, to_iso, utcnow  # noqa: E402
from tracker.store import Store  # noqa: E402
from tracker.watchlist import add_title, validate_ref  # noqa: E402


def session() -> boto3.Session:
    return boto3.Session(profile_name=os.environ.get("AWS_PROFILE", "release-tracker"))


def open_store(stack: str) -> Store:
    s = session()
    outputs = s.client("cloudformation").describe_stacks(StackName=stack)["Stacks"][0]["Outputs"]
    table = next(o["OutputValue"] for o in outputs if o["OutputKey"] == "TableName")
    return Store(table=s.resource("dynamodb").Table(table))


def show(item: WatchItem) -> str:
    nxt = f" | next {item.next_label} @ {to_iso(item.next_release_at)}" if item.next_label else ""
    err = f" | ERROR {item.last_error}" if item.last_error else ""
    return f"{item.ref:50} {item.kind:5} {item.title} | last {item.last_label} (seq {item.last_seq}){nxt}{err}"


def cmd_peek(args):
    snap = sources.FETCHERS[args.source](args.source_id, utcnow(), Decimal(0) if args.all else None)
    print(f"{snap.title} [{snap.status}] {snap.url}")
    for r in snap.released:
        print(f"  {r.key:16} seq={r.seq} {r.label} @ {to_iso(r.released_at)}")
    if snap.upcoming:
        print(f"  next: {snap.upcoming.label} @ {to_iso(snap.upcoming.at)}")


def cmd_add(args):
    source_id = validate_ref(args.source, args.source_id)
    item, created = add_title(open_store(args.stack), args.source, source_id, sources.FETCHERS, utcnow())
    print(("Added " if created else "Already on watchlist: ") + show(item))


def cmd_list(args):
    for item in sorted(open_store(args.stack).list_watchlist(), key=lambda i: i.title.lower()):
        print(show(item))


def cmd_remove(args):
    open_store(args.stack).remove(args.source, args.source_id)
    print(f"Removed {args.source}#{args.source_id}")


def cmd_notifications(args):
    for row in open_store(args.stack).list_notifications(after=args.after):
        print(f"{row['sk']:70} {row['title']}: {row['body']}")


def cmd_rewind(args):
    """Move last-seen state back N releases so the next check sees them as new."""
    store = open_store(args.stack)
    item = store.get(args.source, args.source_id)
    if item is None:
        sys.exit("Not on the watchlist")
    released = sources.FETCHERS[args.source](args.source_id, utcnow(), Decimal(0)).released
    rewound = released[-args.by :]
    item.last_seq = released[-args.by - 1].seq if len(released) > args.by else Decimal(0)
    store.save_state(item)
    print(f"Rewound {item.title} to seq {item.last_seq}; next check sees: {', '.join(r.label for r in rewound)}")
    if args.forget:
        store.forget_releases(item, [r.key for r in rewound])
        print("Forgot their release-log rows, so they will notify again")
    else:
        print("Release-log rows kept: if these were already notified, the checker must skip them")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stack", default="release-tracker")
    sub = parser.add_subparsers(required=True)

    def title_args(p):
        p.add_argument("source", choices=SOURCES)
        p.add_argument("source_id")
        return p

    title_args(sub.add_parser("add")).set_defaults(func=cmd_add)
    title_args(sub.add_parser("remove")).set_defaults(func=cmd_remove)
    peek = title_args(sub.add_parser("peek"))
    peek.add_argument("--all", action="store_true", help="show recent releases, not just the latest")
    peek.set_defaults(func=cmd_peek)
    rewind = title_args(sub.add_parser("rewind"))
    rewind.add_argument("--by", type=int, default=1)
    rewind.add_argument("--forget", action="store_true", help="also delete release-log rows (re-notify)")
    rewind.set_defaults(func=cmd_rewind)
    sub.add_parser("list").set_defaults(func=cmd_list)
    notifications = sub.add_parser("notifications", help="show the feed the app polls")
    notifications.add_argument("--after", help="cursor: only rows after this sort key")
    notifications.set_defaults(func=cmd_notifications)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
