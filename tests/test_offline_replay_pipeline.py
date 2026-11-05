"""End-to-end synthetic replay; no live data or orders."""
from futures_engine.offline_replay_pipeline import process_one

T = 1793738100000
def fixture():
    plan = dict(signal_id="synthetic-1", symbol="SOL/USDT:USDT",
                status="INDICATIVE_PLAN_ONLY_NOT_EXECUTABLE",
                orders_sent=False, execution_authorized=False,
                risk_snapshot_approved=False, side="long",
                entry="100", stop="99", target="102",
                quantity="1", closed_5m_candle_ms=T)
    history = dict(exchange="BINANCE", market="USDT_M_FUTURES",
                   symbol="SOLUSDT", interval="5m",
                   fetched_at_ms=T+600000, closed_through_ms=T+300000,
                   klines=[[T,100,102.5,99.8,102]])
    return plan, history

def test_end_to_end_repeatable(tmp_path):
    p,h = fixture()
    path = tmp_path/"events.sqlite3"
    a = process_one(plan=p, history=h, journal_path=path)
    b = process_one(plan=p, history=h, journal_path=path)
    assert a["journal"]["inserted"] is True
    assert b["journal"]["inserted"] is False
    assert a["summary"]["events"] == b["summary"]["events"] == 1
    assert a["summary"]["closed_hypothetical"] == 1
    assert a["orders_sent"] is False

def test_end_to_end_rejects_unclosed_history(tmp_path):
    p,h = fixture()
    h["fetched_at_ms"] = T + 200000
    import pytest
    with pytest.raises(ValueError):
        process_one(plan=p, history=h, journal_path=tmp_path/"events.sqlite3")
