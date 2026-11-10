"""Causal OHLCV-only feature extraction for Signals V2 research."""
from dataclasses import dataclass
from statistics import mean
from signals_v2.contracts import Candle, DataRejected, FIVE_MINUTES_MS


@dataclass(frozen=True)
class Features:
    atr14: float
    ema_fast: float
    ema_slow: float
    relative_volume: float
    momentum_6: float
    available_at_ms: int


def ema(values: tuple[float, ...], span: int) -> float:
    if not values or type(span) is not int or span < 2 or len(values) < span:
        raise DataRejected("insufficient_ema_history")
    # Explicit seeded SMA; never use future bars or a lookahead initializer.
    result = mean(values[:span])
    alpha = 2 / (span + 1)
    for value in values[span:]:
        result = alpha * value + (1 - alpha) * result
    return result


def features(bars: tuple[Candle, ...]) -> Features:
    if not isinstance(bars, tuple) or len(bars) < 64:
        raise DataRejected("insufficient_feature_history")
    decision_ms = bars[-1].available_at_ms
    for candle in bars:
        candle.validate(FIVE_MINUTES_MS, decision_ms)
    if any(b.open_ms - a.open_ms != FIVE_MINUTES_MS for a, b in zip(bars, bars[1:])):
        raise DataRejected("missing_or_duplicate_bar")
    ranges = [
        max(cur.high-cur.low, abs(cur.high-prev.close), abs(cur.low-prev.close))
        for prev, cur in zip(bars[-15:-1], bars[-14:])
    ]
    atr = mean(ranges)
    if atr <= 0:
        raise DataRejected("zero_atr")
    vol_base = mean(b.volume for b in bars[-21:-1])
    if vol_base <= 0:
        raise DataRejected("zero_volume_baseline")
    closes = tuple(b.close for b in bars)
    return Features(atr, ema(closes, 9), ema(closes, 21),
                    bars[-1].volume / vol_base,
                    closes[-1] / closes[-7] - 1,
                    bars[-1].close_ms(FIVE_MINUTES_MS))
