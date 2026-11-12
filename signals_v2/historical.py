"""Explicit historical replay construction for Signals V2 research.

Historical OHLCV is NOT a live observation log. This adapter deliberately
distinguishes reconstructed candle-close availability from collector timestamps.
It never claims historical order-book, funding, OI or latency provenance.
"""
from dataclasses import dataclass
from hashlib import sha256
from json import dumps
from math import isfinite
from signals_v2.contracts import (
    Candle, DataRejected, MarketSnapshot, MINUTE_MS, FIVE_MINUTES_MS, SYMBOLS,
)


@dataclass(frozen=True)
class HistoricalBars:
    symbol: str
    timeframe_ms: int
    bars: tuple[Candle, ...]
    source: str
    sha256_digest: str
    availability_assumption: str = "HISTORICAL_CANDLE_CLOSE_RECONSTRUCTED"

    def __post_init__(self):
        if self.symbol not in SYMBOLS:
            raise DataRejected("unsupported_symbol")
        if self.timeframe_ms not in (MINUTE_MS, FIVE_MINUTES_MS):
            raise DataRejected("unsupported_timeframe")
        if not self.source or not self.sha256_digest:
            raise DataRejected("missing_provenance")
        if self.availability_assumption != "HISTORICAL_CANDLE_CLOSE_RECONSTRUCTED":
            raise DataRejected("invalid_replay_availability")
        if not self.bars:
            raise DataRejected("no_closed_candles")
        for b in self.bars:
            b.validate(self.timeframe_ms, b.available_at_ms)
            if b.available_at_ms != b.open_ms + self.timeframe_ms:
                raise DataRejected("historical_availability_not_close")
        for a, b in zip(self.bars, self.bars[1:]):
            if b.open_ms - a.open_ms != self.timeframe_ms:
                raise DataRejected("historical_gap_or_duplicate")


def historical_rows(symbol: str, timeframe_ms: int, rows, *,
                    source: str) -> HistoricalBars:
    """Ingest archived OHLCV with explicit, optimistic close-time availability.

    Raw rows must contain [open_ms,open,high,low,close,volume]. Reject gaps,
    duplicate timestamps and unaligned bars rather than silently filling them.
    This is suitable for exploratory OHLCV-only backtests, not claims about
    real-time latency, microstructure or tradeable execution at the same close.
    """
    if symbol not in SYMBOLS or timeframe_ms not in (MINUTE_MS, FIVE_MINUTES_MS):
        raise DataRejected("invalid_symbol_or_timeframe")
    if not isinstance(source, str) or not source.strip():
        raise DataRejected("missing_provenance")
    out = []
    for row in rows:
        if not isinstance(row, (tuple, list)) or len(row) != 6 or type(row[0]) is not int:
            raise DataRejected("invalid_historical_row")
        try:
            values = tuple(float(x) for x in row[1:6])
        except (ValueError, TypeError, OverflowError) as exc:
            raise DataRejected("invalid_historical_row") from exc
        if not all(isfinite(x) for x in values):
            raise DataRejected("nonfinite_ohlcv")
        b = Candle(row[0], *values, row[0] + timeframe_ms)
        b.validate(timeframe_ms, b.available_at_ms)
        out.append(b)
    canonical = [(b.open_ms, b.open, b.high, b.low, b.close, b.volume) for b in out]
    digest = sha256(dumps(canonical, separators=(",", ":")).encode()).hexdigest()
    return HistoricalBars(symbol, timeframe_ms, tuple(out), source, digest)


def replay_snapshot(five: HistoricalBars, one: HistoricalBars, *,
                    decision_ms: int, lookback_five: int = 64,
                    lookback_one: int = 10) -> MarketSnapshot:
    """Return an as-of snapshot, never including a candle closed in future."""
    if five.symbol != one.symbol or five.timeframe_ms != FIVE_MINUTES_MS or one.timeframe_ms != MINUTE_MS:
        raise DataRejected("historical_pair_mismatch")
    if type(decision_ms) is not int or decision_ms <= 0:
        raise DataRejected("invalid_decision_time")
    if type(lookback_five) is not int or type(lookback_one) is not int or lookback_five <= 0 or lookback_one <= 0:
        raise DataRejected("invalid_replay_lookback")
    f = tuple(b for b in five.bars if b.available_at_ms <= decision_ms)[-lookback_five:]
    m = tuple(b for b in one.bars if b.available_at_ms <= decision_ms)[-lookback_one:]
    snapshot = MarketSnapshot(five.symbol, decision_ms, f, m)
    snapshot.validate(min_five=lookback_five, min_one=lookback_one)
    return snapshot
