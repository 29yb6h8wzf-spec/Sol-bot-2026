"""Read-only XRP history: genuine scanner signal through durable paper replay.

Historical replay is not a live or forward-tested trade. No exchange calls.
"""
import json
from decimal import Decimal
from pathlib import Path

import pytest

from futures_engine.verified_strategy_scan import evaluate, to_strategy_candles
from research.paper_auto_replay import replay_saved_scan
from research.paper_independent_verifier import verify_saved_scan

FIXTURE = Path(__file__).parent / "fixtures" / "xrpusdt_verified_20261109.json"


class _OfflineExchange:
    def close(self):
        pass


def _data():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _scanner(data):
    def loader(symbol, timeframe):
        assert symbol == data["symbol"]
        rows = data["five"] if timeframe == "5m" else data["four"]
        return _OfflineExchange(), {}, rows

    return evaluate(data["symbol"], loader=loader, now_ms=data["asof_ms"])


def _replay_bar(row):
    return {
        "open_ms": row[0], "close_ms": row[0] + 300000 - 1,
        "open": row[1],
        "high": row[2], "low": row[3], "close": row[4],
        "confirmed_closed": True,
    }


def test_real_xrp_history_independently_verifies_and_replays(tmp_path):
    data = _data()
    scan = _scanner(data)
    matching = [
        (i, c) for i, c in enumerate(scan["candidates_85_plus"])
        if c["strategy"] == "EMA_ADX" and c["direction"] == "SHORT"
    ]
    assert len(matching) == 1, "historical scanner must produce a genuine candidate"
    index, candidate = matching[0]
    assert candidate["score"] >= 85
    five = to_strategy_candles(data["five"])
    four = to_strategy_candles(data["four"])
    verified = verify_saved_scan(scan, five, four, candidate_index=index)
    assert verified["signal_id"] == candidate["verification"]["signal_id"]
    assert verified["execution_authorized"] is False
    assert all(row[0] + 14400000 <= data["asof_ms"] for row in data["four"])
    assert all(row[0] + 300000 <= data["asof_ms"] for row in data["five"])
    future = [_replay_bar(data["five"][-1])]
    future.extend(_replay_bar(row) for row in data["future"])
    db = str(tmp_path / "real_xrp_history.sqlite3")
    result = replay_saved_scan(
        scan, future, database_path=db, candidate_index=index,
        five_history=five, four_history=four,
    )
    repeat = replay_saved_scan(
        scan, future, database_path=db, candidate_index=index,
        five_history=five, four_history=four,
    )
    assert result["trade"] == repeat["trade"]
    assert Decimal(result["paper_plan"]["entry_mid"]) == Decimal(str(data["future"][0][1]))
    assert result["trade"]["status"] == "EXECUTED_SL"
    assert Decimal(result["trade"]["net_pnl"]) >= Decimal("-1.50")
    assert result["paper_plan"]["paper_only"] is True
    assert Decimal(result["paper_plan"]["estimated_risk_usd"]) <= Decimal("1.50")
    assert Decimal(result["paper_plan"]["estimated_notional"]) <= 300
    assert result["provenance"]["live_authorized"] is False


def test_real_xrp_history_rejects_mismatched_4h_candle(tmp_path):
    data = _data()
    scan = _scanner(data)
    five = to_strategy_candles(data["five"])
    four = to_strategy_candles(data["four"])
    four[-1]["time"] -= 14400000
    with pytest.raises(ValueError, match="history does not match"):
        verify_saved_scan(scan, five, four)
