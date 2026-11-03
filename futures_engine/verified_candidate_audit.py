"""Read-only Binance Futures signal candidate audit.

This module never sends SQS messages or orders. A strategy score is not
independent authorization to execute a trade.
"""
import json
import time
from datetime import datetime, timezone

SYMBOLS = ("BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT")


def audit_candidate(symbol, bars, direction, *, now_ms=None, timeframe_ms=900000):
    if symbol not in SYMBOLS:
        raise ValueError("unsupported symbol")
    if direction not in (None, "long", "short"):
        raise ValueError("invalid direction")
    if not bars or len(bars) < 3:
        raise ValueError("insufficient candles")
    now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
    times = [int(b[0]) for b in bars]
    if any(t % timeframe_ms for t in times):
        raise ValueError("misaligned candle")
    if any(b - a != timeframe_ms for a, b in zip(times, times[1:])):
        raise ValueError("noncontiguous candles")
    if times[-1] + timeframe_ms > now_ms:
        raise ValueError("unfinished candle")
    if now_ms - (times[-1] + timeframe_ms) > timeframe_ms + 120000:
        raise ValueError("stale candles")
    if any(float(b[4]) <= 0 for b in bars):
        raise ValueError("invalid close")
    return {
        "symbol": symbol,
        "direction": direction,
        "closed_candle_ms": times[-1],
        "last_close": str(bars[-1][4]),
        "status": "RESEARCH_CANDIDATE_NOT_EXECUTABLE" if direction else "NO_SIGNAL",
        "score_verified_independently": False,
        "sqs_sent": False,
        "orders_sent": False,
    }


def scan(symbol, *, loader=None, signal_fn=None):
    if loader is None:
        from futures_engine.market import closed_futures_bars
        loader = closed_futures_bars
    if signal_fn is None:
        from futures_engine.core import crossover_signal
        signal_fn = crossover_signal
    exchange, market, bars = loader(symbol, "15m")
    try:
        direction = signal_fn(bars)
        return audit_candidate(symbol, bars, direction)
    finally:
        if hasattr(exchange, "close"):
            exchange.close()


def main():
    for symbol in SYMBOLS:
        try:
            print(json.dumps(scan(symbol), sort_keys=True))
        except Exception as exc:
            print(json.dumps({"symbol": symbol, "status": "BLOCKED", "reason": str(exc), "sqs_sent": False, "orders_sent": False}))


if __name__ == "__main__":
    main()
