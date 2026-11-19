"""Closed-candle, offline-only SOL/XRP strategy replay.

Inputs are preloaded OHLCV rows [open_ms, open, high, low, close, volume].
No exchange calls, execution, SQS, or production gate changes.
"""
from strategies import candidates
from futures_engine.research_setup_score_distribution import ALLOWED_SYMBOLS, summarize_setups

FIVE_MS = 300_000
FOUR_MS = 14_400_000


def _validate(rows, duration):
    if not isinstance(rows, list) or not rows:
        raise ValueError("empty_candles")
    previous = None
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != 6:
            raise ValueError("invalid_candle")
        t, op, high, low, close, volume = row
        if type(t) is not int or t < 0 or t % duration or (
            previous is not None and t - previous != duration):
            raise ValueError("invalid_candle_time_or_gap")
        if any(type(x) not in (float, int) or not (float("-inf") < x < float("inf"))
               for x in (op, high, low, close, volume)):
            raise ValueError("invalid_candle_value")
        if min(op, high, low, close) <= 0 or volume < 0 or low > min(op, close) or high < max(op, close):
            raise ValueError("invalid_ohlcv")
        previous = t


def _strategy_rows(rows):
    return [{"time": r[0], "high": r[2], "low": r[3],
             "close": r[4], "volume": r[5]} for r in rows]


def replay_symbol(symbol, five, four, *, window=240, include_time=False):
    """Replay each closed 5m candle using only 4h candles closed by that time.

    At a 5m candle's close, a 4h bar is usable only when its end <= that close.
    Never use the current, still-open 4h candle (look-ahead prevention).
    """
    if symbol not in ALLOWED_SYMBOLS:
        raise ValueError("unsupported_symbol")
    _validate(five, FIVE_MS)
    _validate(four, FOUR_MS)
    if type(window) is not int or window < 100:
        raise ValueError("invalid_window")
    output = []
    four_end = 0
    for i in range(window - 1, len(five)):
        close_time = five[i][0] + FIVE_MS
        while four_end < len(four) and four[four_end][0] + FOUR_MS <= close_time:
            four_end += 1
        if four_end < 100:
            continue
        five_window = _strategy_rows(five[i - window + 1:i + 1])
        four_window = _strategy_rows(four[max(0, four_end - window):four_end])
        setups, _ = candidates(five_window, four_window)
        scan = {"symbol": symbol, "setups": [
            {"strategy": s["strategy"], "direction": s["direction"], "score": s["score"]}
            for s in setups]}
        if include_time:
            scan["closed_5m_open_ms"] = five[i][0]
        output.append(scan)
    return output


def replay_report(datasets, *, window=240):
    if not isinstance(datasets, dict) or not datasets:
        raise ValueError("empty_datasets")
    if set(datasets) - ALLOWED_SYMBOLS:
        raise ValueError("unsupported_symbol")
    scans = []
    for symbol, series in sorted(datasets.items()):
        if not isinstance(series, dict) or set(series) != {"5m", "4h"}:
            raise ValueError("invalid_timeframes")
        scans.extend(replay_symbol(symbol, series["5m"], series["4h"], window=window))
    if not scans:
        raise ValueError("insufficient_closed_history")
    return summarize_setups(scans)
