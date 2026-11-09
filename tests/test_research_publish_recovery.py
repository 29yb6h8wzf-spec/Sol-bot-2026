"""Offline crash, replay and fencing tests for isolated publish recovery."""
import sqlite3

import pytest

from futures_engine.research_publish_recovery import (
    acknowledge, claim, enqueue, mark_retry,
)


def setup(tmp_path):
    path = str(tmp_path / "recovery.sqlite")
    with sqlite3.connect(path) as db:
        enqueue(db, "research-1")
    return path


def status(path):
    with sqlite3.connect(path) as db:
        return db.execute(
            "SELECT status,message_id,generation FROM research_publish_delivery "
            "WHERE signal_id='research-1'"
        ).fetchone()


def test_crash_before_send_recovers_after_lease(tmp_path):
    path = setup(tmp_path)
    token1 = claim(path, "research-1", now=100)
    assert token1 == 1
    assert claim(path, "research-1", now=101) is None
    token2 = claim(path, "research-1", now=191)
    assert token2 == 2
    acknowledge(path, "research-1", "sqs-123", token2, now=192)
    assert status(path) == ("SENT", "sqs-123", 2)
    assert claim(path, "research-1", now=999) is None


def test_known_send_failure_retries(tmp_path):
    path = setup(tmp_path)
    token = claim(path, "research-1", now=100)
    assert mark_retry(path, "research-1", token) is True
    assert status(path) == ("PENDING", None, 1)
    assert claim(path, "research-1", now=101) == 2


def test_repeated_enqueue_does_not_reset_sent(tmp_path):
    path = setup(tmp_path)
    token = claim(path, "research-1", now=100)
    acknowledge(path, "research-1", "sqs-123", token, now=101)
    with sqlite3.connect(path) as db:
        enqueue(db, "research-1")
    assert status(path) == ("SENT", "sqs-123", 1)


def test_unclaimed_ack_is_rejected(tmp_path):
    path = setup(tmp_path)
    with pytest.raises(ValueError, match="stale or missing"):
        acknowledge(path, "research-1", "sqs-123", 1)
    assert status(path) == ("PENDING", None, 0)


def test_missing_message_id_is_rejected(tmp_path):
    path = setup(tmp_path)
    token = claim(path, "research-1", now=100)
    with pytest.raises(ValueError, match="message id"):
        acknowledge(path, "research-1", "", token)


def test_old_worker_cannot_ack_after_new_lease(tmp_path):
    path = setup(tmp_path)
    old = claim(path, "research-1", now=100)
    current = claim(path, "research-1", now=191)
    assert (old, current) == (1, 2)
    with pytest.raises(ValueError, match="stale or missing"):
        acknowledge(path, "research-1", "old-send", old, now=192)
    acknowledge(path, "research-1", "new-send", current, now=193)
    assert status(path) == ("SENT", "new-send", 2)


def test_old_worker_cannot_reset_new_lease(tmp_path):
    path = setup(tmp_path)
    old = claim(path, "research-1", now=100)
    current = claim(path, "research-1", now=191)
    assert mark_retry(path, "research-1", old) is False
    assert status(path) == ("SENDING", None, current)
    assert mark_retry(path, "research-1", current) is True
    assert status(path) == ("PENDING", None, current)
