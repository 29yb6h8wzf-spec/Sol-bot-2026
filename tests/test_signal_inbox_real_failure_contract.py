"""Real signal_inbox.accept SQLite failure contracts; no AWS/SQS/network."""
import sqlite3
import time

import pytest

from signal_inbox import accept


def payload(sid="research-test-1"):
    return {
        "signal_id": sid,
        "symbol": "SOLUSDT",
        "direction": "long",
        "score": 85,
        "timestamp": int(time.time()),
        "source": "verified_85_score_engine",
    }


def test_real_accept_persists_once(tmp_path):
    db = str(tmp_path / "inbox.sqlite3")
    assert accept(payload(), db=db) is True
    assert accept(payload(), db=db) is False
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM signals").fetchone()[0] == 1


def test_real_accept_rejects_invalid_schema_without_db(tmp_path):
    db = tmp_path / "inbox.sqlite3"
    p = payload()
    p["unexpected"] = "field"
    with pytest.raises(ValueError, match="schema"):
        accept(p, db=str(db))
    assert not db.exists()


def test_real_accept_surfaces_database_operational_failure(tmp_path):
    # A directory cannot be opened as a SQLite database; this models a
    # transient persistence failure that an SQS consumer must NOT ack/delete.
    with pytest.raises(sqlite3.OperationalError):
        accept(payload(), db=str(tmp_path))


def test_real_accept_surfaces_database_lock(tmp_path):
    db = str(tmp_path / "inbox.sqlite3")
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE signals(signal_id TEXT PRIMARY KEY,received_at INTEGER NOT NULL,payload TEXT NOT NULL)")
        conn.commit()
    locker = sqlite3.connect(db, timeout=0)
    try:
        locker.execute("BEGIN EXCLUSIVE")
        with pytest.raises(sqlite3.OperationalError):
            accept(payload(), db=db)
    finally:
        locker.rollback()
        locker.close()
