"""Read-only Binance Futures DEMO fill provenance scan.

No order writes. Does not import historical orders into registry or clear
any risk block. Only hashed order fingerprints are written to the report.
"""
import json
import time
from pathlib import Path

from demo_account_observer import assert_demo, demo_exchange, save_observation
from demo_trade_attribution import fetch_day_trades, registry_orders
from demo_provenance_review import classify_fills

OUTPUT = Path("/opt/signalpilot/demo-provenance-observation.json")


def inspect(exchange, *, registry_path=None, now_ms=None):
    assert_demo(exchange)
    orders, present = registry_orders() if registry_path is None else registry_orders(registry_path)
    day, trades = fetch_day_trades(exchange, now_ms=now_ms)
    fills = [{
        "symbol": t["symbol"], "order_id": t["order_id"],
        "trade_id": t["trade_id"],
        "realized_pnl_usdt": str(t["realized_pnl"]),
        "fee_usdt": str(t["commission"]),
    } for t in trades]
    lookups = []
    for symbol, oid in sorted(set((t["symbol"], t["order_id"]) for t in trades)):
        assert_demo(exchange)
        try:
            order = exchange.fetch_order(oid, symbol)
            valid = (isinstance(order, dict) and str(order.get("id")) == oid
                     and order.get("symbol") == symbol)
            client = order.get("clientOrderId") if valid else None
            lookups.append({"symbol": symbol, "order_id": oid,
                            "confirmed": valid, "client_order_id": client})
        except Exception:
            lookups.append({"symbol": symbol, "order_id": oid,
                            "confirmed": False, "client_order_id": None})
    result = classify_fills(fills, lookups, list(orders.values()))
    result.update({
        "source": "binance_demo_order_provenance_read_only",
        "observed_at": int(time.time()),
        "day_start_utc_ms": day,
        "registry_present": present,
        "scope": "four_symbols_utc_day_only",
    })
    return result


def main():
    exchange = demo_exchange()
    try:
        report = inspect(exchange)
        save_observation(report, OUTPUT)
        public = {k: v for k, v in report.items() if k != "orders"}
        print(json.dumps(public, sort_keys=True))
    finally:
        if hasattr(exchange, "close"):
            exchange.close()


if __name__ == "__main__":
    main()
