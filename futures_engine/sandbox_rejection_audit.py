"""SQLite-backed durable rejection audit for sandbox-only SQS consumer.

Use a dedicated audit DB on persistent disk, never the research or inbox DB.
No queue access, no message bodies, no secrets, and no order execution.
"""
import sqlite3
import time

def record_rejection(*, db_path, message_id, reason):
    if not isinstance(message_id, str) or not message_id:
        raise ValueError("message id required")
    if reason not in ("expired or future signature", "stale candidate"):
        raise ValueError("unsupported terminal rejection")
    with sqlite3.connect(db_path, timeout=10) as conn:
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS sandbox_terminal_rejections "
            "(message_id TEXT PRIMARY KEY, reason TEXT NOT NULL, recorded_at INTEGER NOT NULL)"
        )
        conn.execute(
            "INSERT OR IGNORE INTO sandbox_terminal_rejections "
            "(message_id, reason, recorded_at) VALUES (?, ?, ?)",
            (message_id, reason, int(time.time())),
        )
        existing = conn.execute(
            "SELECT reason FROM sandbox_terminal_rejections WHERE message_id=?",
            (message_id,),
        ).fetchone()
        if existing[0] != reason:
            raise ValueError("audit reason conflict")
