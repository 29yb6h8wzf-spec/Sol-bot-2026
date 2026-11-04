"""SignalPilot read-only research/market interface contracts.

These contracts validate untrusted observations; they never approve trades.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

SYMBOLS = frozenset({"BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"})


def positive_decimal(value):
    if isinstance(value, bool):
        raise ValueError("invalid_numeric")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("invalid_numeric") from None
    if not number.is_finite() or number <= 0:
        raise ValueError("invalid_numeric")
    return number


@dataclass(frozen=True)
class ClosedCandle:
    symbol: str
    open_ms: int
    timeframe_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    @classmethod
    def from_values(cls, *, symbol, open_ms, timeframe_ms, open, high, low, close, volume, now_ms):
        if symbol not in SYMBOLS or type(open_ms) is not int or type(now_ms) is not int:
            raise ValueError("invalid_candle_identity")
        if type(timeframe_ms) is not int or timeframe_ms <= 0 or open_ms < 0:
            raise ValueError("invalid_candle_time")
        if open_ms % timeframe_ms or open_ms + timeframe_ms > now_ms:
            raise ValueError("unclosed_or_misaligned_candle")
        o, h, l, c = (positive_decimal(v) for v in (open, high, low, close))
        if isinstance(volume, bool):
            raise ValueError("invalid_volume")
        try:
            v = Decimal(str(volume))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError("invalid_volume") from None
        if not v.is_finite() or v < 0 or l > min(o, c) or h < max(o, c) or h < l:
            raise ValueError("invalid_ohlcv")
        return cls(symbol, open_ms, timeframe_ms, o, h, l, c, v)
