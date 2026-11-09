"""Read-only research outbox / legacy publish-log reconciliation.

Counts are not delivery evidence. This module never sends or changes rows.
"""
import sqlite3


def compare(db_path):
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as db:
        tables = {
            row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if not {"research_outbox", "sandbox_publish_log"}.issubset(tables):
            raise ValueError("missing research outbox or legacy publish log")
        for table in ("research_outbox", "sandbox_publish_log"):
            columns = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
            if "signal_id" not in columns:
                raise ValueError(f"{table} missing signal_id")
        outbox = db.execute("SELECT COUNT(*) FROM research_outbox").fetchone()[0]
        legacy = db.execute("SELECT COUNT(*) FROM sandbox_publish_log").fetchone()[0]
        only_outbox = db.execute(
            "SELECT COUNT(*) FROM research_outbox o "
            "WHERE NOT EXISTS (SELECT 1 FROM sandbox_publish_log l "
            "WHERE l.signal_id=o.signal_id)"
        ).fetchone()[0]
        only_log = db.execute(
            "SELECT COUNT(*) FROM sandbox_publish_log l "
            "WHERE NOT EXISTS (SELECT 1 FROM research_outbox o "
            "WHERE o.signal_id=l.signal_id)"
        ).fetchone()[0]
        matched = outbox - only_outbox
        return {
            "outbox_rows": outbox,
            "legacy_log_rows": legacy,
            "matched_ids": matched,
            "outbox_without_log": only_outbox,
            "log_without_outbox": only_log,
            "sqs_delivery_confirmed": False,
        }
