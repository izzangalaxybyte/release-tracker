"""DynamoDB access. One table, all timestamps ISO-8601 UTC:

  pk="WATCH"                    sk="{source}#{source_id}"        watchlist entry + last-seen state
  pk="REL#{source}#{source_id}" sk="{release key}"               one row per release ever notified
  pk="NOTIF"                    sk="{created_at}#{source}#{id}"  notification feed the app polls

The REL rows are the idempotency log: a release is only sent by whoever creates its row
(or re-claims it after a recorded send failure), so retries, overlapping runs and state
rewinds can never notify the same release twice.

NOTIF rows sort by creation time, so the app fetches "everything after the last sort key I
saw" as its cursor. They expire via DynamoDB TTL (expires_at) after NOTIFICATION_TTL.
"""

import os
from dataclasses import fields
from datetime import datetime, timedelta
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

from .models import Release, WatchItem, from_iso, to_iso

WATCH_PK = "WATCH"
NOTIF_PK = "NOTIF"
MAX_SEND_ATTEMPTS = 3
NOTIFICATION_TTL = timedelta(days=90)

PENDING, SENT, FAILED = "pending", "sent", "failed"

_DATE_FIELDS = {"added_at", "last_released_at", "next_release_at", "checked_at"}
_STATE_FIELDS = [f.name for f in fields(WatchItem) if f.name not in ("source", "source_id", "added_at")]


def _rel_pk(item: WatchItem) -> str:
    return f"REL#{item.ref}"


def _is_conditional_failure(e: ClientError) -> bool:
    return e.response["Error"]["Code"] == "ConditionalCheckFailedException"


class Store:
    def __init__(self, table_name: str | None = None, table=None):
        self.table = table or boto3.resource("dynamodb").Table(table_name or os.environ["TABLE_NAME"])

    # --- watchlist -------------------------------------------------------------------

    def list_watchlist(self) -> list[WatchItem]:
        return [_item_from_row(row) for row in self._query(KeyConditionExpression=Key("pk").eq(WATCH_PK))]

    def get(self, source: str, source_id: str) -> WatchItem | None:
        row = self.table.get_item(Key={"pk": WATCH_PK, "sk": f"{source}#{source_id}"}).get("Item")
        return _item_from_row(row) if row else None

    def add(self, item: WatchItem) -> bool:
        """Insert a new entry. Returns False if the title is already on the watchlist."""
        try:
            self.table.put_item(Item=_item_to_row(item), ConditionExpression=Attr("pk").not_exists())
            return True
        except ClientError as e:
            if _is_conditional_failure(e):
                return False
            raise

    def remove(self, source: str, source_id: str) -> None:
        self.table.delete_item(Key={"pk": WATCH_PK, "sk": f"{source}#{source_id}"})

    def save_state(self, item: WatchItem) -> bool:
        """Write state fields back. Returns False (and writes nothing) if the entry was removed meanwhile."""
        sets, removes, values = [], [], {}
        names = {f"#{name}": name for name in _STATE_FIELDS}
        for name in _STATE_FIELDS:
            value = _to_dynamo(name, getattr(item, name))
            if value is None:
                removes.append(f"#{name}")
            else:
                sets.append(f"#{name} = :{name}")
                values[f":{name}"] = value
        expression = "SET " + ", ".join(sets)
        if removes:
            expression += " REMOVE " + ", ".join(removes)
        try:
            self.table.update_item(
                Key={"pk": WATCH_PK, "sk": item.ref},
                UpdateExpression=expression,
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
                ConditionExpression=Attr("pk").exists(),
            )
            return True
        except ClientError as e:
            if _is_conditional_failure(e):
                return False
            raise

    # --- release log (idempotency) -----------------------------------------------------

    def claim_release(self, item: WatchItem, release: Release, now: datetime) -> bool:
        """Atomically take the right to notify about a release.

        Succeeds for a release never seen before, or one whose earlier send is recorded as
        failed (with attempts left). A crash after claiming leaves the row "pending", which
        is never re-claimed: at worst a release is missed, never sent twice.
        """
        try:
            self.table.update_item(
                Key={"pk": _rel_pk(item), "sk": release.key},
                UpdateExpression="SET #status = :pending, #label = :label, #seq = :seq, #released_at = :released_at,"
                " #url = :url, #claimed_at = :now ADD #attempts :one",
                ConditionExpression=Attr("pk").not_exists()
                | (Attr("status").eq(FAILED) & Attr("attempts").lt(MAX_SEND_ATTEMPTS)),
                ExpressionAttributeNames={
                    f"#{n}": n for n in ("status", "label", "seq", "released_at", "url", "claimed_at", "attempts")
                },
                ExpressionAttributeValues={
                    ":pending": PENDING,
                    ":label": release.label,
                    ":seq": release.seq,
                    ":released_at": to_iso(release.released_at),
                    ":url": release.url,
                    ":now": to_iso(now),
                    ":one": 1,
                },
            )
            return True
        except ClientError as e:
            if _is_conditional_failure(e):
                return False
            raise

    def mark_release(self, item: WatchItem, release: Release, status: str, now: datetime, error: str | None = None):
        updates = {"status": status, "updated_at": to_iso(now)}
        if error:
            updates["error"] = error[:500]
        self.table.update_item(
            Key={"pk": _rel_pk(item), "sk": release.key},
            UpdateExpression="SET " + ", ".join(f"#{k} = :{k}" for k in updates),
            ExpressionAttributeNames={f"#{k}": k for k in updates},
            ExpressionAttributeValues={f":{k}": v for k, v in updates.items()},
        )

    def retryable_releases(self, item: WatchItem) -> list[Release]:
        rows = self._query(
            KeyConditionExpression=Key("pk").eq(_rel_pk(item)),
            FilterExpression=Attr("status").eq(FAILED) & Attr("attempts").lt(MAX_SEND_ATTEMPTS),
        )
        return [
            Release(key=r["sk"], seq=r["seq"], label=r["label"], released_at=from_iso(r.get("released_at")), url=r.get("url"))
            for r in rows
        ]

    def release_log(self, item: WatchItem) -> list[dict]:
        return self._query(KeyConditionExpression=Key("pk").eq(_rel_pk(item)))

    def forget_releases(self, item: WatchItem, keys: list[str]) -> None:
        """Testing aid: delete release-log rows so those releases can be notified again."""
        with self.table.batch_writer() as batch:
            for key in keys:
                batch.delete_item(Key={"pk": _rel_pk(item), "sk": key})

    # --- notification feed ----------------------------------------------------------

    def add_notification(self, item: WatchItem, title: str, body: str, releases: list[Release], now: datetime) -> str:
        sk = f"{to_iso(now)}#{item.ref}"
        latest = max(releases, key=lambda r: r.seq)
        self.table.put_item(Item={
            "pk": NOTIF_PK,
            "sk": sk,
            "title": title,
            "body": body,
            "kind": item.kind,
            "source": item.source,
            "source_id": item.source_id,
            "url": latest.url or item.url,
            "image": item.image,
            "releases": [{"key": r.key, "label": r.label, "released_at": to_iso(r.released_at)} for r in releases],
            "created_at": to_iso(now),
            "expires_at": int((now + NOTIFICATION_TTL).timestamp()),
        })
        return sk

    def list_notifications(self, after: str | None = None, limit: int = 100) -> list[dict]:
        """Oldest first. `after` is the sort key of the last notification the caller has seen."""
        condition = Key("pk").eq(NOTIF_PK)
        if after:
            condition &= Key("sk").gt(after)
        resp = self.table.query(KeyConditionExpression=condition, ScanIndexForward=True, Limit=limit)
        return resp["Items"]

    # --- helpers ---------------------------------------------------------------------

    def _query(self, **kwargs) -> list[dict]:
        rows = []
        while True:
            resp = self.table.query(**kwargs)
            rows += resp["Items"]
            if "LastEvaluatedKey" not in resp:
                return rows
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def _to_dynamo(name: str, value):
    if name in _DATE_FIELDS:
        return to_iso(value)
    return value


def _item_to_row(item: WatchItem) -> dict:
    row = {"pk": WATCH_PK, "sk": item.ref}
    for f in fields(WatchItem):
        value = _to_dynamo(f.name, getattr(item, f.name))
        if value is not None:
            row[f.name] = value
    return row


def _item_from_row(row: dict) -> WatchItem:
    kwargs = {}
    for f in fields(WatchItem):
        value = row.get(f.name)
        if f.name in _DATE_FIELDS:
            value = from_iso(value)
        elif f.name == "last_seq" and value is not None:
            value = Decimal(value)
        kwargs[f.name] = value
    return WatchItem(**kwargs)
