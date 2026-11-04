"""Read-only Binance USDT-M market data smoke test.

Public candles only. No keys, order methods, paper orders, or live trading.
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .market import closed_futures_bars


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m futures_engine.market_smoke OUTPUT_DIR")
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for symbol in ("BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT"):
        exchange = None
        try:
            exchange, market, bars = closed_futures_bars(symbol, "5m")
            digest = hashlib.sha256(json.dumps(bars, separators=(",", ":")).encode()).hexdigest()
            results.append({
                "symbol": symbol, "status": "ok", "closed_candles": len(bars),
                "first_candle_ms": bars[0][0], "last_candle_ms": bars[-1][0],
                "last_close": bars[-1][4], "bars_sha256": digest,
            })
        except Exception as exc:
            results.append({"symbol": symbol, "status": "error",
                            "error_type": type(exc).__name__, "error": str(exc)[:300]})
        finally:
            if exchange is not None and hasattr(exchange, "close"):
                exchange.close()
    evidence = {
        "mode": "public_market_data_only",
        "source": "binance_usdt_m_futures",
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "timeframe": "5m",
        "authenticated": False,
        "orders_submitted": False,
        "paper_trades_created": False,
        "results": results,
    }
    (output / "market-smoke.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence))
    if any(row["status"] != "ok" for row in results):
        raise SystemExit("market smoke failed; see saved evidence")


if __name__ == "__main__":
    main()
