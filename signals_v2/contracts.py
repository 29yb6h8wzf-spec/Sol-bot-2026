"""Immutable, time-causal market data contracts for research signals only.

The only supported inputs are already-observed, *closed* Binance-style OHLCV
bars. Any missing, stale, duplicated, future or inconsistent data fails closed.
"""
from dataclasses import dataclass
from math import isfinite
from typing import Sequence

MINUTE_MS = 60_000
FIVE_MINUTES_MS = 300_000
SYMBOLS = frozenset(("SOLUSDT", "XRPUSDT"))


class DataRejected(ValueError):
    """A research input is unsafe or not reproducible."""


@dataclass(frozen=True)
class Candle:
    open_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    available_at_ms: int

    def validate(self, duration_ms: int, decision_ms: int) -> None:
        if type(self.open_ms) is not int or type(self.available_at_ms) is not int:
            raise DataRejected("non_integer_timestamp")
        if self.open_ms < 0 or self.open_ms % duration_ms:
            raise DataRejected("misaligned_candle")
        if type(decision_ms) is not int or decision_ms < 0:
            raise DataRejected("invalid_decision_time")
        values = (self.open, self.high, self.low, self.close, self.volume)
        if any(type(v) not in (float, int) or not isfinite(v) for v in values):
            raise DataRejected("nonfinite_ohlcv")
        if min(self.open, self.close, self.low) <= 0 or self.volume < 0:
            raise DataRejected("invalid_ohlcv")
        if not (self.low <= min(self.open, self.close) <=
                max(self.open, self.close) <= self.high):
            raise DataRejected("invalid_high_low")
        close_ms = self.open_ms + duration_ms
        if not close_ms <= self.available_at_ms <= decision_ms:
            raise DataRejected("unavailable_or_unclosed_candle")

    def close_ms(self, duration_ms: int) -> int:
        return self.open_ms + duration_ms


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    decision_ms: int
    five_minute: tuple[Candle, ...]
    one_minute: tuple[Candle, ...]

    def validate(self, *, min_five: int = 32, min_one: int = 10) -> None:
        if self.symbol not in SYMBOLS:
            raise DataRejected("unsupported_symbol")
        if type(self.decision_ms) is not int or self.decision_ms <= 0:
            raise DataRejected("invalid_decision_time")
        for bars, duration, minimum, max_age in (
            (self.five_minute, FIVE_MINUTES_MS, min_five, FIVE_MINUTES_MS * 2),
            (self.one_minute, MINUTE_MS, min_one, MINUTE_MS * 2),
        ):
            if not isinstance(bars, tuple) or len(bars) < minimum:
                raise DataRejected("insufficient_history")
            for bar in bars:
                if not isinstance(bar, Candle):
                    raise DataRejected("invalid_candle_type")
                bar.validate(duration, self.decision_ms)
            for a, b in zip(bars, bars[1:]):
                if b.open_ms - a.open_ms != duration:
                    raise DataRejected("missing_or_duplicate_bar")
                if b.available_at_ms < a.available_at_ms:
                    raise DataRejected("nonmonotonic_availability")
            if not 0 <= self.decision_ms - bars[-1].close_ms(duration) <= max_age:
                raise DataRejected("stale_last_candle")
        # Confirming 1m data may extend past the last closed 5m candle,
        # but may never be older than the last completed 5m candle.
        if self.one_minute[-1].close_ms(MINUTE_MS) < (
            self.five_minute[-1].close_ms(FIVE_MINUTES_MS)
        ):
            raise DataRejected("confirmation_precedes_primary")
        # Cross-feed consistency on overlapping complete 5m intervals:
        # reject a 1m/5m feed mismatch, not merely an aligned timestamp.
        one_by_open = {bar.open_ms: bar for bar in self.one_minute}
        for five in self.five_minute:
            starts = range(five.open_ms, five.open_ms + FIVE_MINUTES_MS, MINUTE_MS)
            if all(t in one_by_open for t in starts):
                one = [one_by_open[t] for t in starts]
                if any(abs(a - b) > max(1e-8, abs(a) * 1e-6) for a, b in (
                    (one[0].open, five.open),
                    (one[-1].close, five.close),
                    (max(x.high for x in one), five.high),
                    (min(x.low for x in one), five.low),
                    (sum(x.volume for x in one), five.volume),
                )):
                    raise DataRejected("cross_timeframe_ohlcv_mismatch")


def from_binance_rows(rows: Sequence[Sequence], *, duration_ms: int,
                      decision_ms: int, observed_at_ms: int) -> tuple[Candle, ...]:
    """Convert Binance OHLCV rows only if observed at/after candle close.

    `observed_at_ms` must be a trusted collector timestamp, not supplied by
    the market feed. Never infer past availability from historical OHLCV.
    """
    if duration_ms not in (MINUTE_MS, FIVE_MINUTES_MS):
        raise DataRejected("unsupported_timeframe")
    if type(observed_at_ms) is not int or type(decision_ms) is not int:
        raise DataRejected("invalid_observation_time")
    if observed_at_ms > decision_ms:
        raise DataRejected("future_observation")
    out = []
    for row in rows:
        if len(row) < 6 or type(row[0]) is not int:
            raise DataRejected("invalid_binance_row")
        open_ms = row[0]
        # An unfinished last candle is dropped, never treated as closed.
        if open_ms + duration_ms > observed_at_ms:
            continue
        try:
            candle = Candle(open_ms, *(float(v) for v in row[1:6]),
                            available_at_ms=observed_at_ms)
        except (TypeError, ValueError, OverflowError) as exc:
            raise DataRejected("invalid_binance_row") from exc
        candle.validate(duration_ms, decision_ms)
        out.append(candle)
    if not out:
        raise DataRejected("no_closed_candles")
    return tuple(out)
