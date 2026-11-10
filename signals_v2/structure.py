"""Deterministic market structure using only confirmed, closed 5m candles.

No retrospective pivot painting: a swing at index i is available only after
`right` later bars have closed. The decision candle cannot retroactively
confirm the swing it is attempting to break.
"""
from dataclasses import dataclass
from typing import Optional
from signals_v2.contracts import Candle, DataRejected, FIVE_MINUTES_MS


@dataclass(frozen=True)
class Pivot:
    index: int
    price: float
    kind: str
    confirmed_at_ms: int


@dataclass(frozen=True)
class StructureObservation:
    trend: str
    event: str
    broken_level: Optional[float]
    latest_resistance: Optional[float]
    latest_support: Optional[float]
    bullish_fvg: bool
    bearish_fvg: bool
    available_at_ms: int
    research_only: bool = True


def confirmed_pivots(bars: tuple[Candle, ...], *, left: int = 2,
                     right: int = 2, through_index: Optional[int] = None
                     ) -> tuple[Pivot, ...]:
    if type(left) is not int or type(right) is not int or min(left, right) < 1:
        raise DataRejected("invalid_pivot_window")
    end = len(bars) - 1 if through_index is None else through_index
    if type(end) is not int or not 0 <= end < len(bars):
        raise DataRejected("invalid_pivot_end")
    pivots = []
    for i in range(left, end - right + 1):
        bar = bars[i]
        neighborhood = bars[i-left:i] + bars[i+1:i+right+1]
        if all(bar.high > other.high for other in neighborhood):
            pivots.append(Pivot(i, bar.high, "HIGH",
                                bars[i+right].close_ms(FIVE_MINUTES_MS)))
        if all(bar.low < other.low for other in neighborhood):
            pivots.append(Pivot(i, bar.low, "LOW",
                                bars[i+right].close_ms(FIVE_MINUTES_MS)))
    return tuple(pivots)


def structure(bars: tuple[Candle, ...], *, left: int = 2,
              right: int = 2) -> StructureObservation:
    if not isinstance(bars, tuple) or len(bars) < max(8, left+right+3):
        raise DataRejected("insufficient_structure_history")
    if any(not isinstance(bar, Candle) for bar in bars):
        raise DataRejected("invalid_candle_type")
    if any(b.open_ms - a.open_ms != FIVE_MINUTES_MS
           for a, b in zip(bars, bars[1:])):
        raise DataRejected("missing_or_duplicate_bar")
    for bar in bars:
        bar.validate(FIVE_MINUTES_MS, bars[-1].available_at_ms)
    current, previous = bars[-1], bars[-2]
    # Require pivot to have been confirmed *before* the event candle opened.
    pivots = confirmed_pivots(bars, left=left, right=right,
                             through_index=len(bars)-2)
    highs = [p for p in pivots if p.kind == "HIGH"
             and p.confirmed_at_ms <= current.open_ms]
    lows = [p for p in pivots if p.kind == "LOW"
            and p.confirmed_at_ms <= current.open_ms]
    resistance = highs[-1].price if highs else None
    support = lows[-1].price if lows else None
    trend = "UNKNOWN"
    if len(highs) >= 2 and len(lows) >= 2:
        if highs[-1].price > highs[-2].price and lows[-1].price > lows[-2].price:
            trend = "UP"
        elif highs[-1].price < highs[-2].price and lows[-1].price < lows[-2].price:
            trend = "DOWN"
        else:
            trend = "RANGE"
    event, level = "NONE", None
    if resistance is not None and previous.close <= resistance < current.close:
        event, level = ("CHOCH_UP" if trend == "DOWN" else "BOS_UP"), resistance
    elif support is not None and previous.close >= support > current.close:
        event, level = ("CHOCH_DOWN" if trend == "UP" else "BOS_DOWN"), support
    elif resistance is not None and current.high > resistance >= current.close:
        event, level = "SWEEP_HIGH", resistance
    elif support is not None and current.low < support <= current.close:
        event, level = "SWEEP_LOW", support
    # Three-bar imbalance is known only at the close of the third bar.
    bullish_fvg = current.low > bars[-3].high
    bearish_fvg = current.high < bars[-3].low
    return StructureObservation(
        trend=trend, event=event, broken_level=level,
        latest_resistance=resistance, latest_support=support,
        bullish_fvg=bullish_fvg, bearish_fvg=bearish_fvg,
        available_at_ms=current.close_ms(FIVE_MINUTES_MS))
