"""Offline contract tests for the tracked research outbox only.

These tests never call AWS, Binance, Telegram, or installed server-only modules.
They do NOT certify the untracked SQS publisher/consumer implementation.
"""
import sqlite3

import pytest

from futures_engine.research_outbox import stage


def candidate(signal_id="research-test-1"):
    verification = {
        "status": "RECALCULATED_RESEARCH_CANDIDATE",
        "score_verified_independently": True,
        "execution_authorized": False,
        "sqs_sent": False,
        "orders_sent": False,
        "symbol": "SOLUSDT",
        "candle_ms": 1730000000000,
        "score": 85,
        "strategy": "EMA_ADX",
        "direction": "LONG",
        "signal_id": signal_id,
    }
    return {
        "status": "RESEARCH_ONLY",
        "symbol": "SOLUSDT",
        "closed_5m_candle_ms": 1730000000000,
        "candidates_85_plus": [
            {"verification": verification, "score": 85, "strategy": "EMA_ADX", "direction": "LONG"}
        ],
    }


def rows(db):
    with sqlite3.connect(db) as conn:
        return conn.execute(
            "SELECT signal_id, state FROM research_outbox ORDER BY signal_id"
        ).fetchall()


def test_stage_retry_is_idempotent(tmp_path):
    db = tmp_path / "outbox.sqlite3"
    event = candidate()
    assert stage(event, db=str(db)) == 1
    assert stage(event, db=str(db)) == 0
    assert rows(db) == [("research-test-1", "PENDING_REVIEW")]


def test_rejects_unverified_candidate_without_persisting(tmp_path):
    db = tmp_path / "outbox.sqlite3"
    event = candidate()
    event["candidates_85_plus"][0]["verification"]["execution_authorized"] = True
    with pytest.raises(ValueError, match="unverified research candidate"):
        stage(event, db=str(db))
    assert rows(db) == []


def test_second_candidate_failure_rolls_back_first(tmp_path):
    db = tmp_path / "outbox.sqlite3"
    event = candidate()
    second = candidate("research-test-2")["candidates_85_plus"][0]
    second["verification"]["orders_sent"] = True
    event["candidates_85_plus"].append(second)
    with pytest.raises(ValueError, match="unverified research candidate"):
        stage(event, db=str(db))
    assert rows(db) == []


def test_non_research_status_never_creates_database(tmp_path):
    db = tmp_path / "outbox.sqlite3"
    event = candidate()
    event["status"] = "LIVE"
    assert stage(event, db=str(db)) == 0
    assert not db.exists()
