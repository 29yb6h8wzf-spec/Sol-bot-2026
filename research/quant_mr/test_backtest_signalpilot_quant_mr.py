"""Deterministic offline no-lookahead portfolio research tests."""
from decimal import Decimal

import pytest

import backtest_signalpilot_quant_mr as bt
import signalpilot_quant_mr as bot


def fixture():
    n = 60
    rows = {}
    for symbol in bot.SYMBOLS:
        trades, mark = [], []
        for i in range(n):
            start = i * bot.INTERVAL_MS
            volume = 20 if i == 21 else 10
            close = 99 if i % 2 else 101
            trades.append([start, "100", str(close + 1.5),
                           str(close - 1.5), str(close), str(volume)])
            mark.append([start, "100", "101", "99", "100", "0"])
        mark[21] = [21 * bot.INTERVAL_MS, "100", "100", "96.5", "97", "0"]
        trades[22][1] = "97"
        trades[22][3] = "96"
        mark[22] = [22 * bot.INTERVAL_MS, "97", "100", "95", "96", "0"]
        rows[symbol] = {"trades": trades, "mark": mark}
    return {"schema": "signalpilot-15m-market-mark-v1",
            "asof_ms": n * bot.INTERVAL_MS, "symbols": rows}


def test_portfolio_two_positions_stop_first_and_fee_adjusted():
    result = bt.simulate(fixture(), 20, 60)
    assert result["counts"]["entries"] == 2
    assert result["closed_trades"] == 2
    assert result["wins"] == 0 and result["losses"] == 2
    assert {t["symbol"] for t in result["trades"]} == set(bot.SYMBOLS)
    assert all(t["status"] == "SL" for t in result["trades"])
    assert all(Decimal(t["margin_allocated_usdt"]) <= Decimal("7.50")
               for t in result["trades"])
    assert all(Decimal(t["net_pnl_usdt"]) < 0 for t in result["trades"])
    assert result["assumptions"]["orders_sent"] is False


def test_future_change_cannot_change_previous_signal():
    snapshot = fixture()
    rows = snapshot["symbols"]["SOL/USDT:USDT"]
    before = bot.signal_from_closed_bars(
        rows["trades"][1:21], rows["trades"][21], Decimal("97"))[0]
    rows["trades"][23][4] = "1000"
    after = bot.signal_from_closed_bars(
        rows["trades"][1:21], rows["trades"][21], Decimal("97"))[0]
    assert before == after == "LONG"


def test_gap_and_unclosed_snapshot_fail_closed():
    snapshot = fixture()
    snapshot["symbols"]["SOL/USDT:USDT"]["trades"][30][0] += bot.INTERVAL_MS
    with pytest.raises(bot.SafetyError, match="Gap or duplicate"):
        bt.validate_snapshot(snapshot)
    snapshot = fixture()
    snapshot["asof_ms"] -= bot.INTERVAL_MS
    with pytest.raises(bot.SafetyError, match="Unclosed"):
        bt.validate_snapshot(snapshot)


def test_mark_trade_timestamp_mismatch_fails_closed():
    snapshot = fixture()
    snapshot["symbols"]["XRP/USDT:USDT"]["mark"][10][0] += bot.INTERVAL_MS
    with pytest.raises(bot.SafetyError):
        bt.validate_snapshot(snapshot)


def test_stop_first_if_both_touched_in_same_bar():
    snapshot = fixture()
    for symbol in bot.SYMBOLS:
        snapshot["symbols"][symbol]["mark"][22] = [
            22 * bot.INTERVAL_MS, "97", "105", "95", "100", "0",
        ]
    result = bt.simulate(snapshot, 20, 60)
    assert result["closed_trades"] == 2
    assert all(t["status"] == "SL" for t in result["trades"])
