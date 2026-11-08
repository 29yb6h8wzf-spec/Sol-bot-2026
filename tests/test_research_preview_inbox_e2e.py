"""Offline integration of real research preview and real inbox persistence.

No SQS, AWS, exchange or production filesystem access.
"""
import json
import sqlite3

import pytest

from futures_engine.research_sqs_preview import preview
from signal_inbox import accept


def record(candle_ms=1_800_000_000_000):
    return {
        "signal_id": "research-verified-001",
        "symbol": "SOL/USDT:USDT",
        "candle_ms": candle_ms,
        "state": "PENDING_REVIEW",
        "payload": {
            "status": "RECALCULATED_RESEARCH_CANDIDATE",
            "score_verified_independently": True,
            "strategy": "EMA_ADX",
            "execution_authorized": False,
            "sqs_sent": False,
            "orders_sent": False,
            "symbol": "SOL/USDT:USDT",
            "candle_ms": candle_ms,
            "signal_id": "research-verified-001",
            "direction": "LONG",
            "score": 85,
        },
    }


def test_real_preview_to_real_inbox_replay_is_idempotent(tmp_path, monkeypatch):
    r = record()
    event_seconds = (r["candle_ms"] + 300000) // 1000
    monkeypatch.setattr("signal_inbox.time.time", lambda: event_seconds)
    wire = preview(r, now=event_seconds)
    assert wire["mode"] == "DRY_RUN_NO_SEND"
    assert wire["authenticated_source"] is False
    assert wire["execution_authorized"] is False
    db = str(tmp_path / "signals.sqlite3")
    assert accept(json.loads(json.dumps(wire["payload"])), db=db) is True
    assert accept(json.loads(json.dumps(wire["payload"])), db=db) is False
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0] == 1


def test_real_preview_blocks_stale_research_before_inbox(tmp_path):
    r = record()
    event_seconds = (r["candle_ms"] + 300000) // 1000
    with pytest.raises(ValueError, match="expired"):
        preview(r, now=event_seconds + 121)
    assert not (tmp_path / "signals.sqlite3").exists()


def test_real_preview_rejects_execution_authorized_flag():
    r = record()
    r["payload"]["execution_authorized"] = True
    event_seconds = (r["candle_ms"] + 300000) // 1000
    with pytest.raises(ValueError, match="research verification mismatch"):
        preview(r, now=event_seconds)
