"""Offline scanner-to-paper integration: no exchange calls or credentials."""
import hashlib
import json
from decimal import Decimal

import pytest

from research.paper_signal_adapter import replay_scanner_candidate


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
        "status": "RESEARCH_ONLY", "orders_sent": False, "sqs_sent": False,
        "symbol": "SOL/USDT:USDT", "closed_5m_candle_ms": 1700000100000,
        "candidates_85_plus": [
            {"strategy": "EMA_ADX", "direction": "LONG", "score": 90,
             "verification": {
                 "status": "RECALCULATED_RESEARCH_CANDIDATE",
                 "score_verified_independently": True,
                 "execution_authorized": False, "orders_sent": False,
                 "sqs_sent": False, "symbol": "SOL/USDT:USDT",
                 "candle_ms": 1700000100000, "strategy": "EMA_ADX",
                 "direction": "LONG", "score": 90,
                 "signal_id": _fixture_signal_id()
             }}
        ],
    }


def bars():
    return [
        {"open_ms": 1700000400000, "close_ms": 1700000699999,
         "high": "105", "low": "99", "close": "104",
         "confirmed_closed": True}
    ]


def run(scan_result, tmp_path, bars_input=None):
    return replay_scanner_candidate(
        scan_result, quantity="1", entry_mid="100", stop="98",
        target="104", bars=bars() if bars_input is None else bars_input,
        database_path=str(tmp_path / "paper.sqlite3"),
    )


def test_scanner_candidate_paper_tp_and_restart_idempotency(tmp_path):
    first = run(scan(), tmp_path)
    second = run(scan(), tmp_path)
    assert first["trade"] == second["trade"]
    assert first["trade"]["status"] == "EXECUTED_TP"
    assert Decimal(first["trade"]["net_pnl"]) < Decimal(first["trade"]["gross_pnl"])
    assert first["provenance"]["paper_only"] is True
    assert first["provenance"]["live_authorized"] is False


def test_rejects_missing_candidate(tmp_path):
    result = scan()
    result["candidates_85_plus"] = []
    with pytest.raises(ValueError, match="no eligible"):
        run(result, tmp_path)


def test_rejects_pre_signal_candle(tmp_path):
    earlier = bars()
    earlier[0]["open_ms"] -= 300000
    with pytest.raises(ValueError, match="signal or earlier"):
        run(scan(), tmp_path, earlier)


def test_rejects_scanner_that_sent_orders(tmp_path):
    result = scan()
    result["orders_sent"] = True
    with pytest.raises(ValueError, match="read-only"):
        run(result, tmp_path)


def test_rejects_forged_verification(tmp_path):
    result = scan()
    result["candidates_85_plus"][0]["verification"]["execution_authorized"] = True
    with pytest.raises(ValueError, match="unverified research candidate"):
        run(result, tmp_path)


def test_rejects_mismatched_signal_candle(tmp_path):
    result = scan()
    result["candidates_85_plus"][0]["verification"]["candle_ms"] += 300000
    with pytest.raises(ValueError, match="unverified research candidate"):
        run(result, tmp_path)


def test_rejects_replay_starting_after_claimed_entry(tmp_path):
    delayed = bars()
    delayed[0]["open_ms"] += 300000
    delayed[0]["close_ms"] += 300000
    with pytest.raises(ValueError, match="start at eligible entry candle"):
        run(scan(), tmp_path, delayed)
    assert not (tmp_path / "paper.sqlite3").exists()
