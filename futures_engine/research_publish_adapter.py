"""Offline publisher orchestration with injected SQS sender.

Caller supplies already validated preview payload, stable signal_id, and
send callable. No AWS, exchange or secrets in this module. This does NOT
replace the EC2-local publisher until reviewed migration/integration.
"""
import sqlite3

from futures_engine.research_publish_recovery import (
    acknowledge, claim, enqueue,
)


def publish_one(db_path, signal_id, send, *, now=None):
    """At-least-once transport; returns state, never assumes exactly-once SQS.

    An exception from send may mean delivery succeeded before an ACK was
    lost. Leave SENDING leased so recovery can retry after expiry.
    Downstream must deduplicate using the stable signal_id.
    """
    with sqlite3.connect(db_path, timeout=15) as db:
        enqueue(db, signal_id)
    token = claim(db_path, signal_id, now=now)
    if token is None:
        return "SKIPPED"
    response = send()
    message_id = response["MessageId"]
    acknowledge(db_path, signal_id, message_id, token, now=now)
    return "SENT"
