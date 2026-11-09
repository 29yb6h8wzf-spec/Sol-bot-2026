"""Isolated SQLite delivery lease with fencing against stale workers.

No network, AWS, secrets or exchange execution. EC2 publisher integration
and migration of its legacy log are separate reviewed work.
"""
import sqlite3
import time

LEASE_SECONDS = 90


def ensure_schema(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS research_publish_delivery ("
        "signal_id TEXT PRIMARY KEY, status TEXT NOT NULL "
        "CHECK(status IN ('PENDING','SENDING','SENT')), "
        "lease_until INTEGER NOT NULL DEFAULT 0, "
        "generation INTEGER NOT NULL DEFAULT 0, "
        "message_id TEXT, sent_at INTEGER)"
    )


def enqueue(db, signal_id):
    ensure_schema(db)
    db.execute(
        "INSERT OR IGNORE INTO research_publish_delivery "
        "(signal_id,status) VALUES (?,'PENDING')", (signal_id,)
    )


def claim(db_path, signal_id, *, now=None):
    """Return unique integer lease generation, or None when not claimable."""
    now = int(time.time()) if now is None else int(now)
    with sqlite3.connect(db_path, timeout=15, isolation_level=None) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            ensure_schema(db)
            row = db.execute(
                "SELECT status,lease_until,generation "
                "FROM research_publish_delivery WHERE signal_id=?", (signal_id,)
            ).fetchone()
            if row is None:
                db.execute("COMMIT")
                return None
            status, lease_until, generation = row
            if status == "SENT" or (status == "SENDING" and lease_until > now):
                db.execute("COMMIT")
                return None
            token = generation + 1
            db.execute(
                "UPDATE research_publish_delivery SET status='SENDING',"
                "lease_until=?,generation=? WHERE signal_id=?",
                (now + LEASE_SECONDS, token, signal_id)
            )
            db.execute("COMMIT")
            return token
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise


def acknowledge(db_path, signal_id, message_id, token, *, now=None):
    now = int(time.time()) if now is None else int(now)
    if not message_id:
        raise ValueError("SQS message id required")
    with sqlite3.connect(db_path, timeout=15) as db:
        cursor = db.execute(
            "UPDATE research_publish_delivery SET status='SENT',"
            "lease_until=0,message_id=?,sent_at=? "
            "WHERE signal_id=? AND status='SENDING' AND generation=?",
            (message_id, now, signal_id, token)
        )
        if cursor.rowcount != 1:
            raise ValueError("stale or missing delivery claim")


def mark_retry(db_path, signal_id, token):
    """Only call when send definitely failed; ambiguous results need replay."""
    with sqlite3.connect(db_path, timeout=15) as db:
        cursor = db.execute(
            "UPDATE research_publish_delivery SET status='PENDING',"
            "lease_until=0 WHERE signal_id=? AND status='SENDING' "
            "AND generation=?",
            (signal_id, token)
        )
        return cursor.rowcount == 1
