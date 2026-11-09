"""Offline automatic replay rejects absent signals and missing future candles."""
import pytest

from research.paper_auto_replay import replay_saved_scan


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
                "signal_id": "research-fixture",
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
    result = replay_saved_scan(scan(), candles(), database_path=str(tmp_path / "paper.db"))
    assert result["trade"]["status"] == "EXECUTED_TP"
    assert result["paper_plan"]["paper_only"] is True
    assert result["provenance"]["live_authorized"] is False


def test_auto_replay_requires_actual_candidate(tmp_path):
    result = scan()
    result["candidates_85_plus"] = []
    with pytest.raises(ValueError, match="no eligible"):
        replay_saved_scan(result, candles(), database_path=str(tmp_path / "paper.db"))


def test_auto_replay_rejects_missing_candle(tmp_path):
    bars = candles()
    bars[1]["open_ms"] += 300000
    with pytest.raises(ValueError, match="gap after signal"):
        replay_saved_scan(scan(), bars, database_path=str(tmp_path / "paper.db"))
