from datetime import datetime, timezone
from decimal import Decimal as D

import pytest

import signalpilot_walkforward as wf
from forex_research import forex_costs, resample_4h
from ftmo_cost_sensitivity import compare
from signalpilot_walkforward import _prague_midnights, evaluate

DAY = 86400000
STEP = 300000
# Monday 2026-11-02 00:00 UTC
MON = int(datetime(2026, 11, 2, tzinfo=timezone.utc).timestamp() * 1000)


def bars(n, step, base):
    return [[base + i * step, 100, 101, 99, 100, 1000] for i in range(n)]


def forex_week(weeks=7, price=1.1):
    """Forex-like history: Sun 22:00 .. Fri 21:55 UTC each week, closed on weekends."""
    rows = []
    for w in range(weeks):
        start = MON - 2 * 3600000 + w * 7 * DAY  # Sunday 22:00 UTC
        t, close = start, start + 5 * DAY
        while t < close:
            rows.append([t, price, price + 0.001, price - 0.001, price, 100]); t += STEP
    return rows


CAND = {"strategy": "EMA_ADX", "threshold": 70, "stop_atr": "1", "target_atr": "1.5", "hold": 3}
COSTS = dict(price="1.1", pip="0.0001", commission_round_turn_per_lot="5", swap_daily_rate="0")


def fake_candidates(monkeypatch, atr=0.002):
    setup = [{"strategy": "EMA_ADX", "direction": "LONG", "score": 90, "atr": atr}]
    monkeypatch.setattr(wf, "candidates", lambda f, h: (setup, None))


def mean(res):
    d = res["thresholds"]["70"]
    return d["sum_net_return_pct_uncompounded"] / d["trades"]


def test_defaults_unchanged_without_spread(monkeypatch):
    fake_candidates(monkeypatch, atr=2)
    five, four = bars(400, STEP, 14400000 * 200), bars(250, 14400000, 0)
    a = evaluate(five, four, thresholds=(70,), max_holding_bars=3)
    b = evaluate(five, four, thresholds=(70,), max_holding_bars=3, spread_rate="0", swap_daily_rate="0")
    assert a["thresholds"] == b["thresholds"]


def test_spread_reduces_return_by_one_spread(monkeypatch):
    fake_candidates(monkeypatch, atr=2)
    five, four = bars(400, STEP, 14400000 * 200), bars(250, 14400000, 0)
    base = mean(evaluate(five, four, thresholds=(70,), max_holding_bars=3))
    wide = mean(evaluate(five, four, thresholds=(70,), max_holding_bars=3, spread_rate="0.002"))
    assert base - wide == pytest.approx(0.2, abs=0.01)


@pytest.mark.parametrize("bad", [dict(spread_rate="-0.001"), dict(spread_rate="0.05"),
                                 dict(swap_daily_rate="-1"), dict(spread_rate="nan")])
def test_invalid_costs_rejected(bad):
    with pytest.raises(ValueError, match="invalid_assumptions"):
        evaluate(bars(400, STEP, 14400000 * 200), bars(250, 14400000, 0), **bad)


def test_weekend_gap_only_allowed_when_requested():
    five = forex_week()
    four = resample_4h(five)
    with pytest.raises(ValueError, match="gapped_candles"):
        evaluate(five, four)
    assert evaluate(five, four, allow_market_closures=True)["orders_sent"] is False


def test_midweek_gap_still_rejected():
    five = forex_week()
    del five[500]  # Tuesday hole
    with pytest.raises(ValueError, match="gapped_candles"):
        evaluate(five, resample_4h(five), allow_market_closures=True)


def test_resample_4h_utc_aligned():
    four = resample_4h(forex_week())
    assert all(r[0] % 14400000 == 0 for r in four)
    assert four[1][5] == D(48 * 100)


def test_forex_costs_eurusd():
    c = forex_costs(price="1.1", spread_pips="0.5", commission_round_turn_per_lot="5", pip="0.0001")
    assert D(c["spread_rate"]) == D("0.00005") / D("1.1")
    assert D(c["fee_rate"]) == D("2.5") / D("110000")


def test_forex_costs_usdjpy_quote_conversion():
    c = forex_costs(price="150", spread_pips="1", commission_round_turn_per_lot="5", pip="0.01",
                    quote_to_usd=D(1) / D(150))
    assert D(c["fee_rate"]) == pytest.approx(D("2.5") / D("100000"))


def test_prague_midnight_count_dst_aware():
    start = 1795473000000  # 2026-11-23 22:30 UTC = 23:30 CET
    assert _prague_midnights(start, start + 3600000) == 1
    assert _prague_midnights(start - 7200000, start) == 0


def test_compare_reports_spread_grid(monkeypatch):
    fake_candidates(monkeypatch)
    out = compare(forex_week(), CAND, **COSTS)
    assert out["orders_sent"] is False and out["ftmo_assumptions_verified"] is False
    means = [x["mean_net_pct"] for x in out["ftmo"]]
    assert means == sorted(means, reverse=True)
    assert out["gross_no_costs"]["mean_net_pct"] > means[0]


def test_compare_requires_costs_and_valid_strategy():
    with pytest.raises(TypeError):
        compare(forex_week(), CAND, price="1.1", pip="0.0001")
    with pytest.raises(ValueError, match="invalid_strategy"):
        compare(forex_week(), dict(CAND, strategy="X"), **COSTS)


def test_load_m5_fills_short_gaps_only(tmp_path):
    from forex_research import load_m5_tsv
    p = tmp_path / "x.csv"
    p.write_text("Time\tOpen\tHigh\tLow\tClose\tVolume\n"
                 "2023-01-02 00:00:00\t1\t1.1\t0.9\t1.05\t5\n"
                 "2023-01-02 00:15:00\t1\t1.1\t0.9\t1\t5\n"
                 "2023-01-02 09:00:00\t1\t1.1\t0.9\t1\t5\n")
    rows = load_m5_tsv(p)
    assert [r[0] - rows[0][0] for r in rows[:4]] == [0, 300000, 600000, 900000]
    assert rows[1][4] == D("1.05") and rows[1][5] == 0
    assert rows[-1][0] - rows[-2][0] > 4 * 3600000  # long gap left for the replay to judge
