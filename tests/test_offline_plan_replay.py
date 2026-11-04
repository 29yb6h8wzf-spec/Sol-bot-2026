"""Offline deterministic regression tests. No credentials or exchange connections."""
import pytest
from futures_engine.offline_plan_replay import replay

T = 1793738100000
def plan(**changes):
    p = dict(status="INDICATIVE_PLAN_ONLY_NOT_EXECUTABLE",
             orders_sent=False, execution_authorized=False,
             risk_snapshot_approved=False, side="long",
             entry="100", stop="99", target="102", quantity="1",
             closed_5m_candle_ms=T)
    p.update(changes)
    return p

def test_stop_and_target_same_bar_chooses_stop():
    r = replay(plan(), [(T,100,103,98,101)])
    assert r["status"] == "CLOSED_HYPOTHETICAL" and r["exit_reason"] == "STOP"
    assert float(r["net_pnl_excluding_funding"]) < 0

def test_target():
    r = replay(plan(), [(T,100,102.5,99.8,102)])
    assert r["exit_reason"] == "TARGET"

def test_no_exit_is_not_realized_profit():
    r = replay(plan(), [(T,100,101,99.9,100.5)])
    assert r["status"] == "OPEN_HYPOTHETICAL"
    assert "net_pnl_excluding_funding" not in r

def test_missing_candles_unknown():
    r = replay(plan(), [(T,100,101,99.9,100), (T+600000,100,101,99,100)])
    assert r["status"] == "UNKNOWN"

def test_no_lookahead_missing_entry():
    r = replay(plan(), [(T+300000,100,103,98,100)])
    assert r["status"] == "UNKNOWN"

def test_gap_through_stop_rejected():
    r = replay(plan(), [(T,98,99,97,98)])
    assert r["status"] == "REJECTED"

def test_risk_cap_rejected():
    r = replay(plan(quantity="3"), [(T,100,101,99.8,100)])
    assert r["status"] == "REJECTED"

def test_execution_must_remain_disabled():
    with pytest.raises(ValueError):
        replay(plan(orders_sent=True), [(T,100,101,99,100)])

def test_bad_ohlc_rejected():
    with pytest.raises(ValueError):
        replay(plan(), [(T,100,99,98,101)])
