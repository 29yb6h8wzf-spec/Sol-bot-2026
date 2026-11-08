"""Read-only legacy migration safety checks; no network or production DB."""
import sqlite3

import pytest

from futures_engine.research_publish_legacy_audit import (
    audit_legacy, classify_legacy_for_migration,
)


def test_missing_legacy_table_is_empty(tmp_path):
    db = tmp_path / "legacy.sqlite"
    with sqlite3.connect(db):
        pass
    assert audit_legacy(str(db))["rows"] == 0
    assert classify_legacy_for_migration(str(db))["requires_manual_reconciliation"] == 0


def test_existing_legacy_row_requires_manual_reconciliation(tmp_path):
    db = tmp_path / "legacy.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE sandbox_publish_log "
            "(signal_id TEXT PRIMARY KEY, message_id TEXT NOT NULL, sent_at INTEGER NOT NULL)"
        )
        conn.execute(
            "INSERT INTO sandbox_publish_log VALUES (?,?,?)",
            ("research-1", "PENDING", 0),
        )
    report = audit_legacy(str(db))
    assert report["rows"] == 1
    assert report["auto_replay_safe"] is False
    with pytest.raises(RuntimeError, match="manual SQS reconciliation"):
        classify_legacy_for_migration(str(db))


def test_legacy_sent_looking_row_is_still_ambiguous(tmp_path):
    db = tmp_path / "legacy.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE sandbox_publish_log "
            "(signal_id TEXT PRIMARY KEY, message_id TEXT NOT NULL, sent_at INTEGER NOT NULL)"
        )
        conn.execute(
            "INSERT INTO sandbox_publish_log VALUES (?,?,?)",
            ("research-2", "sqs-message-123", 12345),
        )
    assert audit_legacy(str(db))["requires_manual_reconciliation"] == 1


def test_schema_mismatch_fails_closed(tmp_path):
    db = tmp_path / "legacy.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE sandbox_publish_log (signal_id TEXT)")
    with pytest.raises(ValueError, match="schema"):
        audit_legacy(str(db))
