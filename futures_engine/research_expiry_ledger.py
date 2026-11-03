"""Idempotent expiry ledger for research outbox; never changes original rows.

A separate ledger is required because research_outbox has a CHECK constraint
that permits only PENDING_REVIEW. No orders, SQS writes, or deletions.
"""
import json
import sqlite3
import time

from futures_engine.research_outbox import DB


def mark_expired(*, db=DB, now=None, dry_run=True):
    now = int(time.time()) if now is None else int(now)
    with sqlite3.connect(db, timeout=15) as conn:
        rows = conn.execute(
            "SELECT signal_id FROM research_outbox "
            "WHERE state='PENDING_REVIEW' AND candle_ms+300000 < ?",
            ((now - 120) * 1000,),
        ).fetchall()
        if dry_run:
            return {"mode": "DRY_RUN", "expired_candidates": len(rows),
                    "newly_recorded": 0, "orders_enabled": False}
        conn.execute(
            "CREATE TABLE IF NOT EXISTS research_outbox_expiry "
            "(signal_id TEXT PRIMARY KEY, expired_recorded_at INTEGER NOT NULL, "
            "reason TEXT NOT NULL)"
        )
        changed = 0
        for (sid,) in rows:
            result = conn.execute(
                "INSERT OR IGNORE INTO research_outbox_expiry VALUES (?,?,?)",
                (sid, now, "CANDLE_CLOSE_PLUS_120_SECONDS"),
            )
            changed += result.rowcount
        return {"mode": "RECORD_EXPIRY_ONLY", "expired_candidates": len(rows),
                "newly_recorded": changed, "orders_enabled": False}


if __name__ == "__main__":
    import sys
    print(json.dumps(mark_expired(dry_run="--apply" not in sys.argv),
                     sort_keys=True))
