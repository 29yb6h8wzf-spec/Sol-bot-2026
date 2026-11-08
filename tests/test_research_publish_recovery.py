"""Offline crash/replay tests for the isolated recovery state machine."""
import sqlite3

import pytest

from futures_engine.research_publish_recovery import (
    acknowledge, claim, enqueue, ensure_schema, mark_retry,
)


def setup(tmp_path):
    path = str(tmp_path / "recovery.sqlite")
    with sqlite3.connect(path) as db:
        enqueue(db, "research-1")
    return path


def status(path):
    with sqlite3.connect(path) as db:
        return db.execute(
            "SELECT status,message_id FROM research_publish_delivery "
            "WHERE signal_id='research-1'"
        ).fetchone()


def test_crash_before_send_recovers_after_lease(tmp_path):
    path = setup(tmp_path)
    assert claim(path, "research-1", now=100)
    assert not claim(path, "research-1", now=101)
    assert claim(path, "research-1", now=191)
    acknowledge(path, "research-1", "sqs-123", now=192)
    assert status(path) == ("SENT", "sqs-123")
    assert not claim(path, "research-1", now=999)


def test_known_send_failure_retries(tmp_path):
    path = setup(tmp_path)
    assert claim(path, "research-1", now=100)
    mark_retry(path, "research-1")
    assert status(path) == ("PENDING", None)
    assert claim(path, "research-1", now=101)


def test_repeated_enqueue_does_not_reset_sent(tmp_path):
    path = setup(tmp_path)
    assert claim(path, "research-1", now=100)
    acknowledge(path, "research-1", "sqs-123", now=101)
    with sqlite3.connect(path) as db:
        enqueue(db, "research-1")
    assert status(path) == ("SENT", "sqs-123")


def test_unclaimed_ack_is_rejected(tmp_path):
    path = setup(tmp_path)
    with pytest.raises(ValueError, match="not claimed"):
        acknowledge(path, "research-1", "sqs-123")
    assert status(path) == ("PENDING", None)


def test_missing_message_id_is_rejected(tmp_path):
    path = setup(tmp_path)
    assert claim(path, "research-1", now=100)
    with pytest.raises(ValueError, match="message id"):
        acknowledge(path, "research-1", "")
