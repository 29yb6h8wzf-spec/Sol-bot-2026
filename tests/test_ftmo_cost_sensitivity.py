from decimal import Decimal as D

import pytest

import signalpilot_walkforward as wf
from ftmo_cost_sensitivity import compare
from signalpilot_walkforward import _prague_midnights, evaluate

DAY = 86400000


def bars(n, step, base):
    return [[base + i * step, 100, 101, 99, 100, 1000] for i in range(n)]


FIVE = bars(400, 300000, 14400000 * 200)
FOUR = bars(250, 14400000, 0)
CAND = {"strategy": "EMA_ADX", "threshold": 70, "stop_atr": "1", "target_atr": "1.5", "hold": 3}


def fake_candidates(monkeypatch):
    setup = [{"strategy": "EMA_ADX", "direction": "LONG", "score": 90, "atr": 2}]
    monkeypatch.setattr(wf, "candidates", lambda f, h: (setup, None))


def mean(res):
    d = res["thresholds"]["70"]
    return d["sum_net_return_pct_uncompounded"] / d["trades"]


def test_defaults_unchanged_without_spread(monkeypatch):
    fake_candidates(monkeypatch)
    a = evaluate(FIVE, FOUR, thresholds=(70,), max_holding_bars=3)
    b = evaluate(FIVE, FOUR, thresholds=(70,), max_holding_bars=3, spread_rate="0", swap_daily_rate="0")
    assert a["thresholds"] == b["thresholds"]


def test_spread_strictly_reduces_return(monkeypatch):
    fake_candidates(monkeypatch)
    base = mean(evaluate(FIVE, FOUR, thresholds=(70,), max_holding_bars=3))
    wide = mean(evaluate(FIVE, FOUR, thresholds=(70,), max_holding_bars=3, spread_rate="0.002"))
    assert wide < base
    assert base - wide == pytest.approx(0.2, abs=0.01)  # ~one full spread per round trip


@pytest.mark.parametrize("bad", [dict(spread_rate="-0.001"), dict(spread_rate="0.05"),
                                 dict(swap_daily_rate="-1"), dict(spread_rate="nan")])
def test_invalid_costs_rejected(bad):
    with pytest.raises(ValueError, match="invalid_assumptions"):
        evaluate(FIVE, FOUR, **bad)


def test_prague_midnight_count_dst_aware():
    # 2026-11-23 22:30 UTC (23:30 CET) -> 23:30 UTC (00:30 CET): one rollover
    start = 1795473000000
    assert _prague_midnights(start, start + 3600000) == 1
    assert _prague_midnights(start - 7200000, start) == 0
    assert _prague_midnights(start, start + 2 * DAY) == 2


def test_compare_reports_breakeven(monkeypatch):
    fake_candidates(monkeypatch)
    out = compare(FIVE, FOUR, CAND, swap_daily_rate="0")
    assert out["orders_sent"] is False and out["ftmo_assumptions_verified"] is False
    means = [x["mean_net_pct"] for x in out["ftmo"]]
    assert means == sorted(means, reverse=True)
    assert out["binance"]["trades"] > 0


def test_compare_requires_swap_and_valid_strategy():
    with pytest.raises(TypeError):
        compare(FIVE, FOUR, CAND)
    with pytest.raises(ValueError, match="invalid_strategy"):
        compare(FIVE, FOUR, dict(CAND, strategy="X"), swap_daily_rate="0")
