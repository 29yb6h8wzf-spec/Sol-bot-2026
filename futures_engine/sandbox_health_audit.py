"""Read-only health audit for the SignalPilot sandbox research pipeline.

No queue receives, deletes, sends, production inbox writes, or trading.
Run: python -m futures_engine.sandbox_health_audit
"""
import json
import os
import sqlite3
import time

import boto3

from futures_engine.sandbox_research_publisher import QUEUE
from futures_engine.research_outbox import DB as OUTBOX_DB
from futures_engine.sandbox_research_consumer import DB as RECEIVED_DB


def _scalar(path, sql, params=()):
    if not os.path.isfile(path):
        return None
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5) as conn:
        try:
            row = conn.execute(sql, params).fetchone()
        except sqlite3.OperationalError:
            return None
        return row[0] if row else None


def audit(*, sqs=None, now=None, outbox_db=OUTBOX_DB, received_db=RECEIVED_DB):
    now = int(time.time()) if now is None else int(now)
    sqs = sqs or boto3.client("sqs", region_name="il-central-1")
    attrs = sqs.get_queue_attributes(
        QueueUrl=QUEUE,
        AttributeNames=["ApproximateNumberOfMessages",
                        "ApproximateNumberOfMessagesNotVisible",
                        "ApproximateAgeOfOldestMessage"],
    )["Attributes"]
    visible = int(attrs.get("ApproximateNumberOfMessages", 0))
    in_flight = int(attrs.get("ApproximateNumberOfMessagesNotVisible", 0))
    oldest = int(attrs.get("ApproximateAgeOfOldestMessage", 0))
    unconfirmed = _scalar(
        outbox_db,
        "SELECT COUNT(*) FROM sandbox_publish_log WHERE message_id='UNCONFIRMED'",
    )
    published = _scalar(
        outbox_db,
        "SELECT COUNT(*) FROM sandbox_publish_log WHERE message_id!='UNCONFIRMED'",
    )
    received = _scalar(received_db, "SELECT COUNT(*) FROM sandbox_received")
    pending = _scalar(outbox_db,
                      "SELECT COUNT(*) FROM research_outbox WHERE state='PENDING_REVIEW'")
    stale_pending = _scalar(
        outbox_db,
        "SELECT COUNT(*) FROM research_outbox WHERE state='PENDING_REVIEW' "
        "AND (candle_ms+300000) < ?",
        ((now - 120) * 1000,),
    )
    alerts = []
    if unconfirmed is None:
        alerts.append("PUBLISH_LOG_UNAVAILABLE")
    elif unconfirmed:
        alerts.append("UNCONFIRMED_SEND_REQUIRES_MANUAL_RECONCILIATION")
    if received is None:
        alerts.append("RECEIVED_DB_UNAVAILABLE")
    if visible > 0 and oldest > 120:
        alerts.append("OLD_SANDBOX_QUEUE_MESSAGES")
    if in_flight:
        alerts.append("SANDBOX_MESSAGES_IN_FLIGHT")
    return {
        "mode": "READ_ONLY_SANDBOX_HEALTH",
        "timestamp": now,
        "queue": {"visible_approx": visible, "in_flight_approx": in_flight,
                  "oldest_seconds_approx": oldest},
        "outbox": {"pending": pending, "stale_pending": stale_pending,
                   "published": published, "unconfirmed": unconfirmed},
        "consumer": {"stored_total": received},
        "alerts": alerts,
        "status": "CHECK" if alerts else "OK",
        "orders_enabled": False,
        "execution_authorized": False,
        "notes": "SQS counts are approximate; totals are cumulative, not delivery reconciliation.",
    }


if __name__ == "__main__":
    print(json.dumps(audit(), sort_keys=True))
