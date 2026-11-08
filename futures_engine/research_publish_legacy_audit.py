"""Read-only assessment of legacy publisher rows before migration.

Legacy sandbox_publish_log has no durable state; an existing row does not
prove SQS accepted the message. Never auto-mark or resend legacy rows.
"""
import sqlite3


def audit_legacy(db_path):
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as db:
        found = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='sandbox_publish_log'"
        ).fetchone()
        if not found:
            return {"legacy_table": False, "rows": 0, "requires_manual_reconciliation": 0}
        cols = {
            row[1] for row in db.execute("PRAGMA table_info(sandbox_publish_log)")
        }
        required = {"signal_id", "message_id", "sent_at"}
        if not required.issubset(cols):
            raise ValueError("unexpected legacy publish log schema")
        count = db.execute("SELECT COUNT(*) FROM sandbox_publish_log").fetchone()[0]
        return {
            "legacy_table": True,
            "rows": count,
            "requires_manual_reconciliation": count,
            "auto_replay_safe": False,
        }


def classify_legacy_for_migration(db_path):
    """No automatic migration of ambiguous legacy delivery state."""
    report = audit_legacy(db_path)
    if report["requires_manual_reconciliation"]:
        raise RuntimeError(
            "legacy publish log contains ambiguous rows; manual SQS reconciliation required"
        )
    return report
