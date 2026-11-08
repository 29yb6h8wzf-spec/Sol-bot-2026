"""Isolated crash-recovery state machine for research SQS publishing.

No AWS client, secrets, network calls, or exchange execution. Integration into
the EC2-local publisher is a separate reviewed step. SQLite timestamps in seconds.
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
        "message_id TEXT, sent_at INTEGER)"
    )


def enqueue(db, signal_id):
    ensure_schema(db)
    db.execute(
        "INSERT OR IGNORE INTO research_publish_delivery "
        "(signal_id,status) VALUES (?,'PENDING')", (signal_id,)
    )


def claim(db_path, signal_id, *, now=None):
    now = int(time.time()) if now is None else int(now)
    with sqlite3.connect(db_path, timeout=15, isolation_level=None) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            ensure_schema(db)
            row = db.execute(
                "SELECT status,lease_until FROM research_publish_delivery "
                "WHERE signal_id=?", (signal_id,)
            ).fetchone()
            if row is None:
                db.execute("ROLLBACK")
                return False
            status, lease_until = row
            if status == "SENT" or (status == "SENDING" and lease_until > now):
                db.execute("ROLLBACK")
                return False
            db.execute(
                "UPDATE research_publish_delivery "
                "SET status='SENDING',lease_until=? WHERE signal_id=?",
                (now + LEASE_SECONDS, signal_id)
            )
            db.execute("COMMIT")
            return True
        except BaseException:
            db.execute("ROLLBACK")
            raise


def acknowledge(db_path, signal_id, message_id, *, now=None):
    now = int(time.time()) if now is None else int(now)
    if not message_id:
        raise ValueError("SQS message id required")
    with sqlite3.connect(db_path, timeout=15) as db:
        cursor = db.execute(
            "UPDATE research_publish_delivery SET status='SENT',"
            "lease_until=0,message_id=?,sent_at=? "
            "WHERE signal_id=? AND status='SENDING'",
            (message_id, now, signal_id)
        )
        if cursor.rowcount != 1:
            raise ValueError("delivery not claimed")


def mark_retry(db_path, signal_id):
    # Only used when the caller KNOWS send did not succeed.
    # For ambiguous network failures, let the lease expire; replay may
    # duplicate the SQS transport message, so consumer must deduplicate.
    with sqlite3.connect(db_path, timeout=15) as db:
        db.execute(
            "UPDATE research_publish_delivery SET status='PENDING',"
            "lease_until=0 WHERE signal_id=? AND status='SENDING'",
            (signal_id,)
        )
