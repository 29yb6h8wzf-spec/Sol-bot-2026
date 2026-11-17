"""Regression tests for the agreed 48-bar closed-candle evaluation window."""
import pytest
from futures_engine.offline_plan_replay import replay

T = 1793738100000

def plan():
    return dict(status="INDICATIVE_PLAN_ONLY_NOT_EXECUTABLE",
                orders_sent=False, execution_authorized=False,
                risk_snapshot_approved=False, side="long",
                entry="100", stop="99", target="102",
                quantity="1", closed_5m_candle_ms=T)

def candles(count):
    return [[T + i * 300000, 100, 100.5, 99.8, 100] for i in range(count)]

def test_late_target_after_48_bars_is_not_a_win():
    bars = candles(49)
    bars[48] = [T + 48 * 300000, 100, 103, 99.8, 102]
    result = replay(plan(), bars)
    assert result["status"] == "UNKNOWN"
    assert result["reason"] == "evaluation_horizon_elapsed"
    assert "net_pnl_excluding_funding" not in result
    assert result["orders_sent"] is False

def test_target_on_last_eligible_bar_counts():
    bars = candles(48)
    bars[47] = [T + 47 * 300000, 100, 103, 99.8, 102]
    result = replay(plan(), bars)
    assert result["status"] == "CLOSED_HYPOTHETICAL"
    assert result["exit_reason"] == "TARGET"

def test_no_hit_at_48_bars_is_neutral():
    result = replay(plan(), candles(48))
    assert result["status"] == "UNKNOWN"
    assert result["reason"] == "evaluation_horizon_elapsed"

def test_short_history_remains_open_and_unrealized():
    result = replay(plan(), candles(3))
    assert result["status"] == "OPEN_HYPOTHETICAL"
    assert "net_pnl_excluding_funding" not in result

def test_invalid_horizon_rejected():
    with pytest.raises(ValueError, match="invalid_horizon"):
        replay(plan(), candles(1), max_candles=0)
