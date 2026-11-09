"""End-to-end offline injected-send crash contracts."""
import sqlite3

import pytest

from futures_engine.research_publish_adapter import publish_one


def test_send_once_then_skip(tmp_path):
    db = str(tmp_path / "delivery.sqlite")
    calls = []
    def send():
        calls.append("send")
        return {"MessageId": "sqs-1"}
    assert publish_one(db, "research-1", send, now=100) == "SENT"
    assert publish_one(db, "research-1", send, now=200) == "SKIPPED"
    assert calls == ["send"]


def test_ambiguous_send_failure_leaves_lease_and_replays(tmp_path):
    db = str(tmp_path / "delivery.sqlite")
    calls = []
    def ambiguous():
        calls.append("transport accepted but ack lost")
        raise TimeoutError("ambiguous")
    with pytest.raises(TimeoutError):
        publish_one(db, "research-1", ambiguous, now=100)
    assert publish_one(db, "research-1", ambiguous, now=101) == "SKIPPED"
    def recovered():
        calls.append("replay")
        return {"MessageId": "sqs-2"}
    assert publish_one(db, "research-1", recovered, now=191) == "SENT"
    assert len(calls) == 2


def test_missing_message_id_does_not_mark_sent(tmp_path):
    db = str(tmp_path / "delivery.sqlite")
    with pytest.raises(KeyError):
        publish_one(db, "research-1", lambda: {}, now=100)
    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT status FROM research_publish_delivery"
        ).fetchone()[0] == "SENDING"
