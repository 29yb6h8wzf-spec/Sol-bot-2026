"""Cross-feature regressions: 4h evaluation cap and 15-90m exits."""
import pytest
from futures_engine.offline_plan_replay import replay

T = 1793738100000

def plan():
    return {"status": "INDICATIVE_PLAN_ONLY_NOT_EXECUTABLE",
            "orders_sent": False, "execution_authorized": False,
            "risk_snapshot_approved": False, "side": "long",
            "entry": "100", "stop": "99", "target": "102",
            "quantity": "1", "closed_5m_candle_ms": T}

def candles(n):
    return [[T + i*300000, 100, 100.5, 99.8, 100] for i in range(n)]

@pytest.mark.parametrize("minutes", [15, 30, 60, 90])
def test_time_exit_precedes_default_48_bar_horizon(minutes):
    r = replay(plan(), candles(48), max_holding_minutes=minutes)
    assert r["status"] == "CLOSED_HYPOTHETICAL"
    assert r["exit_reason"] == "TIME_LIMIT"
    assert r["exit_candle_ms"] == T + (minutes//5-1)*300000
    assert r["orders_sent"] is False

def test_90_minute_target_happens_before_time_limit():
    data = candles(48)
    data[16] = [T + 16*300000, 100, 103, 99.8, 102]
    r = replay(plan(), data, max_holding_minutes=90)
    assert r["status"] == "CLOSED_HYPOTHETICAL"
    assert r["exit_reason"] == "TARGET"
    assert r["exit_candle_ms"] == T + 16*300000

def test_both_brackets_on_90_minute_expiry_choose_stop():
    data = candles(18)
    data[17] = [T + 17*300000, 100, 103, 98, 100]
    r = replay(plan(), data, max_holding_minutes=90)
    assert r["exit_reason"] == "STOP"
    assert float(r["net_pnl_excluding_funding"]) < 0

def test_48_bar_cap_preempts_incompatible_late_time_exit():
    r = replay(plan(), candles(48), max_holding_minutes=300)
    assert r["status"] == "UNKNOWN"
    assert r["reason"] == "evaluation_horizon_elapsed"
    assert "net_pnl_excluding_funding" not in r

def test_shorter_explicit_window_preempts_90_minute_time_exit():
    r = replay(plan(), candles(18), max_candles=12,
               max_holding_minutes=90)
    assert r["status"] == "UNKNOWN"
    assert r["reason"] == "evaluation_horizon_elapsed"

def test_missing_full_90_minute_window_is_unrealized():
    r = replay(plan(), candles(17), max_holding_minutes=90)
    assert r["status"] == "OPEN_HYPOTHETICAL"
    assert "net_pnl_excluding_funding" not in r

def test_execution_authorization_rejected_in_integrated_engine():
    p = plan()
    p["execution_authorized"] = True
    with pytest.raises(ValueError, match="execution_not_disabled"):
        replay(p, candles(18), max_holding_minutes=90)
