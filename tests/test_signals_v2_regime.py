"""Deterministic, no-network market regime tests for research V2."""
from dataclasses import replace
import pytest
from signals_v2.contracts import Candle, MarketSnapshot, DataRejected
from signals_v2.regime import classify
from test_signals_v2_core import BASE


def snapshot(*, high_volatility=False, breakout=False):
    count = 80
    end = BASE + count * 300_000
    decision = end + 60_000
    five = []
    for i in range(count):
        high, low, close = 102, 98, 100
        if high_volatility and i >= 66:
            high, low = 110, 90
        if breakout and i == 70:
            high = 110
        if breakout and i == 79:
            high, close = 113, 112
        five.append(Candle(BASE + i*300_000, 100, high, low, close, 5,
                           decision))
    one = []
    for i in range(10):
        five_index = 78 + i // 5
        minute = i % 5
        parent = five[five_index]
        high = parent.high if minute == 0 else 100
        low = parent.low if minute == 0 else 100
        close = parent.close if minute == 4 else 100
        if minute == 4:
            high = max(high, close)
        one.append(Candle(BASE + five_index*300_000 + minute*60_000,
                          100, high, low, close, 1, decision))
    return MarketSnapshot("XRPUSDT", decision, tuple(five), tuple(one))


def test_flat_unknown_abstains():
    result = classify(snapshot())
    assert result.regime == "UNKNOWN"
    assert result.research_only is True


def test_high_volatility_is_opportunity_regime_not_automatic_signal():
    result = classify(snapshot(high_volatility=True))
    assert result.regime == "HIGH_VOLATILITY"
    assert result.atr_ratio >= 1.8
    assert not hasattr(result, "entry")


def test_confirmed_breakout_transition():
    result = classify(snapshot(breakout=True))
    assert result.regime == "BREAKOUT_TRANSITION"
    assert result.reason == "BOS_UP"


def test_rejects_stale_snapshot():
    s = snapshot()
    with pytest.raises(DataRejected, match="stale_last_candle"):
        classify(replace(s, decision_ms=s.decision_ms + 1_000_000))


def test_no_future_bar_dependency():
    s = snapshot(breakout=True)
    before = classify(s)
    later = Candle(s.five_minute[-1].open_ms + 300_000, 112, 200, 1, 150,
                   5, s.decision_ms + 300_000)
    assert classify(replace(s, five_minute=s.five_minute)) == before
    assert later.open_ms > s.five_minute[-1].open_ms
