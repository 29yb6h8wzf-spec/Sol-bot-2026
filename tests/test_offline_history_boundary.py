"""Offline history boundary tests; all data is synthetic."""
import pytest
from futures_engine.offline_history_boundary import replay_verified_history

T = 1793738100000
def plan():
    return {"status": "INDICATIVE_PLAN_ONLY_NOT_EXECUTABLE",
            "orders_sent": False, "execution_authorized": False,
            "risk_snapshot_approved": False, "symbol": "SOL/USDT:USDT",
            "side": "long", "entry": "100", "stop": "99",
            "target": "102", "quantity": "1",
            "closed_5m_candle_ms": T}
def history():
    return {"exchange": "BINANCE", "market": "USDT_M_FUTURES",
            "symbol": "SOLUSDT", "interval": "5m",
            "fetched_at_ms": T + 600000, "closed_through_ms": T + 300000,
            "klines": [[T, 100, 102.5, 99.8, 102]]}

def test_reproducible_hash_and_hypothetical_result():
    a = replay_verified_history(plan(), history())
    b = replay_verified_history(plan(), history())
    assert a["history_sha256"] == b["history_sha256"]
    assert a["result"]["exit_reason"] == "TARGET"
    assert a["orders_sent"] is False
    assert "UNVERIFIED" in a["source"]

@pytest.mark.parametrize("field,value", [
    ("exchange", "KRAKEN"), ("market", "SPOT"), ("interval", "1m"),
    ("symbol", "ADAUSDT"), ("closed_through_ms", T),
])
def test_bad_provenance_blocked(field, value):
    h = history()
    h[field] = value
    with pytest.raises(ValueError):
        replay_verified_history(plan(), h)

def test_open_candle_blocked():
    h = history()
    h["closed_through_ms"] = T + 600000
    h["klines"].append([T+300000,100,101,99,100])
    h["fetched_at_ms"] = T + 450000
    with pytest.raises(ValueError):
        replay_verified_history(plan(), h)

def test_mismatched_symbol_blocked():
    p = plan()
    p["symbol"] = "ETH/USDT:USDT"
    with pytest.raises(ValueError):
        replay_verified_history(p, history())

def test_missing_history_blocked():
    h = history()
    h["klines"] = []
    with pytest.raises(ValueError):
        replay_verified_history(plan(), h)
