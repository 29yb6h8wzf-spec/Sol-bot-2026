"""Read-only alternate-market OHLCV smoke for research and paper validation.

Kraken spot candles are NOT Binance USDT-M futures prices.
Never sends orders or silently substitutes a data source.
"""
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

SYMBOLS = ("BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT")


def inspect(symbol, timeframe="5m"):
    import ccxt
    exchange = ccxt.kraken({"enableRateLimit": True, "timeout": 15000})
    try:
        markets = exchange.load_markets()
        market = markets.get(symbol)
        if not market or not market.get("spot") or market.get("active") is False:
            raise ValueError("requested active spot market unavailable")
        duration = exchange.parse_timeframe(timeframe) * 1000
        rows = exchange.fetch_ohlcv(symbol, timeframe, limit=240)
        now = exchange.milliseconds()
        if not isinstance(rows, list) or not rows:
            raise ValueError("empty or malformed spot response")
        for row in rows:
            if (not isinstance(row, (list, tuple)) or len(row) < 6
                or any(isinstance(value, bool) or not isinstance(value, (int, float))
                       or not math.isfinite(value) for value in row[:6])):
                raise ValueError("invalid nonfinite or malformed spot candle")
        closed = [r for r in rows if r[0] + duration <= now]
        if len(closed) < 100:
            raise ValueError("insufficient closed candles")
        for index, row in enumerate(closed):
            t, o, h, l, c, v = row[:6]
            if (t < 0 or t % duration or min(o, h, l, c) <= 0 or v < 0
                or not l <= o <= h or not l <= c <= h
                or (index and t - closed[index - 1][0] != duration)):
                raise ValueError("invalid or gapped spot candles")
        if now - (closed[-1][0] + duration) > duration + 120000:
            raise ValueError("stale spot candles")
        return {"symbol": symbol, "status": "ok", "closed_candles": len(closed),
                "last_candle_ms": closed[-1][0], "last_close": closed[-1][4]}
    finally:
        exchange.close()


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m futures_engine.alternate_market_smoke OUTPUT_DIR")
    directory = Path(sys.argv[1])
    directory.mkdir(parents=True, exist_ok=True)
    results = []
    for symbol in SYMBOLS:
        try:
            results.append(inspect(symbol))
        except Exception as exc:
            results.append({"symbol": symbol, "status": "error",
                            "error_type": type(exc).__name__, "error": str(exc)[:250]})
    report = {"mode": "research_data_only", "exchange": "kraken",
              "market_type": "spot", "not_binance_futures": True,
              "orders_submitted": False, "paper_trades_created": False,
              "collected_at_utc": datetime.now(timezone.utc).isoformat(),
              "timeframe": "5m", "results": results}
    (directory / "alternate-market-smoke.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    if any(row["status"] != "ok" for row in results):
        raise SystemExit("alternate market smoke failed; see evidence")


if __name__ == "__main__":
    main()
