"""Offline automatic replay rejects absent signals and missing future candles."""
import hashlib
import json
from unittest.mock import patch

import pytest

from research.paper_auto_replay import replay_saved_scan


def _fixture_signal_id():
    fields = {
        "symbol": "SOL/USDT:USDT", "strategy": "EMA_ADX",
        "direction": "LONG", "score": 90,
        "candle_ms": 1700000100000,
    }
    return "research-" + hashlib.sha256(
        json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:32]


def scan():
    return {
        "symbol": "SOL/USDT:USDT", "status": "RESEARCH_ONLY",
        "orders_sent": False, "sqs_sent": False,
        "closed_5m_candle_ms": 1700000100000,
        "candidates_85_plus": [{
            "strategy": "EMA_ADX", "direction": "LONG", "score": 90,
            "verification": {
                "status": "RECALCULATED_RESEARCH_CANDIDATE",
                "score_verified_independently": True,
                "execution_authorized": False, "orders_sent": False,
                "sqs_sent": False, "symbol": "SOL/USDT:USDT",
                "candle_ms": 1700000100000, "strategy": "EMA_ADX",
                "direction": "LONG", "score": 90,
                "signal_id": _fixture_signal_id(),
            },
        }],
    }


def candles():
    return [
        {"open_ms": 1700000100000, "close_ms": 1700000399999,
         "high": "101", "low": "99", "close": "100", "confirmed_closed": True},
        {"open_ms": 1700000400000, "close_ms": 1700000699999,
         "high": "103", "low": "99", "close": "102", "confirmed_closed": True},
    ]


def test_auto_replay_sized_paper_trade(tmp_path):
    with patch("research.paper_auto_replay.verify_saved_scan"):
        result = replay_saved_scan(scan(), candles(), database_path=str(tmp_path / "paper.db"), five_history=[{}], four_history=[{}])
    assert result["trade"]["status"] == "EXECUTED_SL"
    assert result["paper_plan"]["paper_only"] is True
    assert result["provenance"]["live_authorized"] is False


def test_auto_replay_requires_actual_candidate(tmp_path):
    result = scan()
    result["candidates_85_plus"] = []
    with (patch("research.paper_auto_replay.verify_saved_scan", side_effect=ValueError("no eligible scanner candidate")),
          pytest.raises(ValueError, match="no eligible")):
            replay_saved_scan(result, candles(), database_path=str(tmp_path / "paper.db"), five_history=[{}], four_history=[{}])


def test_auto_replay_rejects_missing_candle(tmp_path):
    bars = candles()
    bars[1]["open_ms"] += 300000
    with (patch("research.paper_auto_replay.verify_saved_scan"),
          pytest.raises(ValueError, match="gap after signal")):
            replay_saved_scan(scan(), bars, database_path=str(tmp_path / "paper.db"), five_history=[{}], four_history=[{}])


def test_auto_replay_rejects_missing_independent_history(tmp_path):
    with pytest.raises(ValueError, match="independent 5m and 4h"):
        replay_saved_scan(scan(), candles(), database_path=str(tmp_path / "paper.db"))
