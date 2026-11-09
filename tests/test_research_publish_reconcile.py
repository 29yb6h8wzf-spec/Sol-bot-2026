"""Read-only reconciliation contracts."""
import sqlite3

import pytest

from futures_engine.research_publish_reconcile import compare


def seed(tmp_path):
    path = tmp_path / "research.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE research_outbox (signal_id TEXT PRIMARY KEY)")
        db.execute(
            "CREATE TABLE sandbox_publish_log "
            "(signal_id TEXT PRIMARY KEY, message_id TEXT, sent_at INTEGER)"
        )
        db.executemany(
            "INSERT INTO research_outbox VALUES (?)",
            [("a",), ("b",), ("c",)]
        )
        db.executemany(
            "INSERT INTO sandbox_publish_log VALUES (?,?,?)",
            [("a", "sqs-1", 100), ("z", "PENDING", 0)]
        )
    return path


def test_set_difference_not_count_subtraction(tmp_path):
    result = compare(str(seed(tmp_path)))
    assert result["outbox_rows"] == 3
    assert result["legacy_log_rows"] == 2
    assert result["matched_ids"] == 1
    assert result["outbox_without_log"] == 2
    assert result["log_without_outbox"] == 1
    assert result["sqs_delivery_confirmed"] is False


def test_reconciliation_does_not_write(tmp_path):
    path = seed(tmp_path)
    before = path.read_bytes()
    compare(str(path))
    assert path.read_bytes() == before


def test_missing_tables_fail_closed(tmp_path):
    path = tmp_path / "empty.sqlite"
    with sqlite3.connect(path):
        pass
    with pytest.raises(ValueError, match="missing"):
        compare(str(path))
