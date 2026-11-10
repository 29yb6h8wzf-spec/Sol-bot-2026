"""Causal OHLCV and non-repainting structure tests. No exchange connections."""
from dataclasses import replace
import pytest
from signals_v2.contracts import (
    Candle, MarketSnapshot, DataRejected, MINUTE_MS, FIVE_MINUTES_MS,
    from_binance_rows,
)
from signals_v2.structure import confirmed_pivots, structure

BASE = 1_800_000_000_000


def bar(i, *, duration=FIVE_MINUTES_MS, o=100, h=102, l=98, c=101,
        v=5, observed=None):
    start = BASE + i * duration
    return Candle(start, o, h, l, c, v,
                  start + duration if observed is None else observed)


def snapshot():
    end = BASE + 40 * FIVE_MINUTES_MS
    decision = end + 60_000
    five = tuple(replace(bar(i), available_at_ms=decision) for i in range(40))
    one = []
    for i in range(10):
        # Last two 5m bars, each composed of five matching 1m bars.
        five_i = 38 + i // 5
        minute_i = i % 5
        one.append(Candle(BASE + five_i * FIVE_MINUTES_MS + minute_i * MINUTE_MS,
                          100 if minute_i == 0 else 100,
                          102 if minute_i == 0 else 101,
                          98 if minute_i == 0 else 100,
                          101 if minute_i == 4 else 100, 1,
                          decision))
    return MarketSnapshot("SOLUSDT", decision, five, tuple(one))


def test_valid_cross_timeframe_closed_snapshot():
    snapshot().validate()


def test_rejects_future_and_unclosed_candle():
    s = snapshot()
    future = replace(s.five_minute[-1], available_at_ms=s.decision_ms + 1)
    with pytest.raises(DataRejected, match="unavailable"):
        replace(s, five_minute=s.five_minute[:-1] + (future,)).validate()
    with pytest.raises(DataRejected, match="unavailable"):
        replace(s, decision_ms=s.five_minute[-1].open_ms + 10_000).validate()


def test_rejects_duplicate_or_gapped_bars():
    s = snapshot()
    duplicate = replace(s.five_minute[-1], open_ms=s.five_minute[-2].open_ms)
    with pytest.raises(DataRejected, match="missing_or_duplicate"):
        replace(s, five_minute=s.five_minute[:-1] + (duplicate,)).validate()


def test_rejects_stale_and_mismatched_timeframes():
    s = snapshot()
    with pytest.raises(DataRejected, match="stale_last_candle"):
        replace(s, decision_ms=s.decision_ms + 700_000,
                five_minute=tuple(replace(b, available_at_ms=s.decision_ms)
                                  for b in s.five_minute),
                one_minute=tuple(replace(b, available_at_ms=s.decision_ms)
                                 for b in s.one_minute)).validate()
    changed = replace(s.one_minute[-1], close=100)
    with pytest.raises(DataRejected, match="cross_timeframe"):
        replace(s, one_minute=s.one_minute[:-1] + (changed,)).validate()


def test_rejects_wrong_symbol_and_nonfinite_price():
    s = snapshot()
    with pytest.raises(DataRejected, match="unsupported_symbol"):
        replace(s, symbol="BTCUSDT").validate()
    invalid = replace(s.five_minute[-1], high=float("nan"))
    with pytest.raises(DataRejected, match="nonfinite"):
        replace(s, five_minute=s.five_minute[:-1] + (invalid,)).validate()


def test_binance_adapter_drops_unfinished_bar():
    decision = BASE + 3 * FIVE_MINUTES_MS
    rows = [[BASE + i * FIVE_MINUTES_MS, 100, 102, 98, 101, 5]
            for i in range(4)]
    bars = from_binance_rows(rows, duration_ms=FIVE_MINUTES_MS,
                             decision_ms=decision, observed_at_ms=decision)
    assert len(bars) == 3
    assert bars[-1].open_ms == BASE + 2 * FIVE_MINUTES_MS


def test_binance_adapter_rejects_observation_from_future():
    with pytest.raises(DataRejected, match="future_observation"):
        from_binance_rows([[BASE, 100, 102, 98, 101, 5]],
                          duration_ms=FIVE_MINUTES_MS,
                          decision_ms=BASE + FIVE_MINUTES_MS,
                          observed_at_ms=BASE + FIVE_MINUTES_MS + 1)


def structure_bars(*, breakout_close=17, breakout_high=18):
    highs = [11, 12, 16, 12, 11, 12, 13, breakout_high]
    return tuple(Candle(BASE + i * FIVE_MINUTES_MS, 10, high, 9,
                        breakout_close if i == 7 else 10, 5,
                        BASE + (i+1) * FIVE_MINUTES_MS)
                 for i, high in enumerate(highs))


def test_pivot_only_exists_after_two_confirming_candles():
    bars = structure_bars()
    assert not any(p.index == 2 for p in confirmed_pivots(bars[:4]))
    pivots = confirmed_pivots(bars[:5])
    assert any(p.index == 2 and p.kind == "HIGH" and
               p.confirmed_at_ms == bars[4].close_ms(FIVE_MINUTES_MS)
               for p in pivots)


def test_breakout_is_bos_only_after_confirmed_pivot():
    bars = structure_bars()
    observed = structure(bars)
    assert observed.latest_resistance == 16
    assert observed.event == "BOS_UP"
    assert observed.broken_level == 16
    assert observed.research_only is True
    assert observed.available_at_ms == bars[-1].close_ms(FIVE_MINUTES_MS)


def test_wick_only_is_liquidity_sweep_not_breakout():
    bars = structure_bars(breakout_close=15)
    assert structure(bars).event == "SWEEP_HIGH"


def test_no_lookahead_from_future_candles():
    bars = structure_bars()
    observed = structure(bars)
    extended = bars + (
        Candle(BASE + 8 * FIVE_MINUTES_MS, 17, 40, 1, 18, 5,
               BASE + 9 * FIVE_MINUTES_MS),
    )
    assert structure(extended[:8]) == observed


def test_structure_rejects_missing_bar():
    bars = structure_bars()
    broken = bars[:5] + bars[6:]
    with pytest.raises(DataRejected, match="missing_or_duplicate"):
        structure(broken)
