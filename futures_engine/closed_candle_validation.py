"""Strict read-only validation for Binance Futures OHLCV."""
from market_contracts import ClosedCandle, SYMBOLS


class CandleValidationError(ValueError):
    pass


def validate_rows(symbol, timeframe_ms, rows, now_ms, minimum=202):
    if symbol not in SYMBOLS or type(timeframe_ms) is not int or timeframe_ms <= 0:
        raise CandleValidationError("invalid_market")
    if not isinstance(rows, list):
        raise CandleValidationError("invalid_rows")
    closed = []
    previous = None
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            raise CandleValidationError("malformed_row")
        if type(row[0]) is not int:
            raise CandleValidationError("invalid_timestamp")
        if row[0] + timeframe_ms > now_ms:
            continue
        try:
            ClosedCandle.from_values(
                symbol=symbol, open_ms=row[0], timeframe_ms=timeframe_ms,
                open=row[1], high=row[2], low=row[3], close=row[4],
                volume=row[5], now_ms=now_ms)
        except ValueError as exc:
            raise CandleValidationError("invalid_candle") from exc
        if previous is not None and row[0] - previous != timeframe_ms:
            raise CandleValidationError("gap_or_duplicate")
        previous = row[0]
        closed.append(row)
    if len(closed) < minimum:
        raise CandleValidationError("insufficient_closed_candles")
    if now_ms - (closed[-1][0] + timeframe_ms) > timeframe_ms + 120000:
        raise CandleValidationError("stale_candles")
    return closed
