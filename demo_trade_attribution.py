"""Read-only Binance USDT-M DEMO trade ownership audit.

A trade belongs to SignalPilot ONLY if a trusted local execution registry
identifies its Binance order ID and a read-back of Binance's clientOrderId
confirms the same SPDEMO- identifier. No registry is created here.
This is a partial four-symbol audit, NEVER a risk approval or a trade executor.
"""
import json
import hashlib
import os
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from demo_account_observer import demo_exchange, assert_demo, save_observation

SYMBOLS = ("BTC/USDT:USDT", "ETH/USDT:USDT",
           "SOL/USDT:USDT", "XRP/USDT:USDT")
REGISTRY = Path("/opt/signalpilot/demo-execution-registry.json")
OUTPUT = "/opt/signalpilot/demo-trade-attribution.json"
LIMIT = 1000


def decimal(value):
    try:
        x = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        raise ValueError("invalid_trade_number") from None
    if not x.is_finite():
        raise ValueError("nonfinite_trade_number")
    return x


def registry_orders(path=REGISTRY):
    """Read root-owned registry; absence means zero trusted SignalPilot orders."""
    path = Path(path)
    if not path.exists():
        return {}, False
    st = path.stat()
    if not path.is_file() or st.st_uid != 0 or st.st_mode & 0o077:
        raise ValueError("untrusted_registry_permissions")
    doc = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(doc, dict) or doc.get("schema_version") != 1 or
            doc.get("source") != "signalpilot_demo_executor_registry" or
            doc.get("execution_mode") != "binance_demo" or
            not isinstance(doc.get("orders"), list)):
        raise ValueError("invalid_registry_schema")
    orders = {}
    clients = set()
    for row in doc["orders"]:
        if not isinstance(row, dict):
            raise ValueError("invalid_registry_row")
        symbol, oid, client, sid = (row.get(k) for k in
                                    ("symbol", "order_id", "client_order_id", "signal_id"))
        leg = row.get("leg")
        if (symbol not in SYMBOLS or not isinstance(oid, str) or
                not oid.isdecimal() or not isinstance(client, str) or
                not isinstance(sid, str) or not 1 <= len(sid) <= 128 or
                leg not in ("entry", "stop", "target")):
            raise ValueError("invalid_registry_identity")
        expected = "SPDEMO-" + hashlib.sha256(
            (sid + ":" + leg).encode("utf-8")).hexdigest()[:24]
        if client != expected:
            raise ValueError("registry_client_id_signal_mismatch")
        key = (symbol, oid)
        if key in orders or client in clients:
            raise ValueError("duplicate_registry_identity")
        orders[key] = row
        clients.add(client)
    return orders, True


def fetch_day_trades(exchange, *, now_ms=None, limit=LIMIT):
    assert_demo(exchange)
    now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
    if type(now_ms) is not int or now_ms <= 0 or not 1 <= limit <= 1000:
        raise ValueError("invalid_trade_query")
    midnight = datetime.fromtimestamp(now_ms / 1000, timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0)
    start = int(midnight.timestamp() * 1000)
    trades = []
    ids = set()
    for symbol in SYMBOLS:
        assert_demo(exchange)
        batch = exchange.fetch_my_trades(symbol, since=start, limit=limit)
        if not isinstance(batch, list) or len(batch) >= limit:
            raise ValueError("incomplete_trade_history")
        for trade in batch:
            if not isinstance(trade, dict) or trade.get("symbol") != symbol:
                raise ValueError("invalid_trade_symbol")
            ts = trade.get("timestamp")
            oid = trade.get("order")
            tid = trade.get("id")
            if (type(ts) is not int or not start <= ts <= now_ms or
                    not isinstance(oid, (str, int)) or not str(oid).isdecimal() or
                    not isinstance(tid, (str, int)) or not str(tid)):
                raise ValueError("invalid_trade_identity")
            key = (symbol, str(tid))
            if key in ids:
                raise ValueError("duplicate_trade_id")
            ids.add(key)
            fee = trade.get("fee")
            if not isinstance(fee, dict) or fee.get("currency") != "USDT":
                raise ValueError("unreconciled_trade_fee")
            fee_cost = decimal(fee.get("cost"))
            info = trade.get("info")
            if not isinstance(info, dict) or "realizedPnl" not in info:
                raise ValueError("missing_realized_pnl")
            realized = decimal(info["realizedPnl"])
            if fee_cost < 0:
                raise ValueError("invalid_fee")
            trades.append({"symbol": symbol, "order_id": str(oid),
                           "trade_id": str(tid), "realized_pnl": realized,
                           "commission": fee_cost})
    return start, trades


def audit(exchange, *, registry_path=REGISTRY, now_ms=None):
    assert_demo(exchange)
    orders, registry_present = registry_orders(registry_path)
    start, trades = fetch_day_trades(exchange, now_ms=now_ms)
    confirmed = {}
    for symbol, oid in sorted(set((t["symbol"], t["order_id"]) for t in trades)
                              & set(orders)):
        assert_demo(exchange)
        order = exchange.fetch_order(oid, symbol)
        if (not isinstance(order, dict) or str(order.get("id")) != oid or
                order.get("symbol") != symbol or
                order.get("clientOrderId") != orders[(symbol, oid)]["client_order_id"]):
            raise ValueError("exchange_order_provenance_mismatch")
        confirmed[(symbol, oid)] = orders[(symbol, oid)]
    owned = [t for t in trades if (t["symbol"], t["order_id"]) in confirmed]
    unknown = [t for t in trades if (t["symbol"], t["order_id"]) not in confirmed]
    realized = sum((t["realized_pnl"] for t in owned), Decimal("0"))
    fees = sum((t["commission"] for t in owned), Decimal("0"))
    return {
        "source": "binance_demo_four_symbol_trade_attribution_read_only",
        "observed_at": int(time.time()),
        "day_start_utc_ms": start,
        "registry_present": registry_present,
        "trusted_registry_orders": len(orders),
        "confirmed_order_count": len(confirmed),
        "signalpilot_fills": len(owned),
        "unattributed_fills": len(unknown),
        "signalpilot_realized_pnl_usdt": str(realized),
        "signalpilot_commissions_usdt": str(fees),
        "signalpilot_net_before_funding_usdt": str(realized - fees),
        "scope": "four_symbols_only_funding_and_other_symbols_not_reconciled",
        "allocation_ledger_reconciled": False,
        "risk_snapshot_approved": False,
        "execution_authorized": False,
        "orders_sent": False,
        "status": "AUDIT_ONLY_NOT_EXECUTABLE",
    }


def main():
    exchange = demo_exchange()
    try:
        result = audit(exchange)
        save_observation(result, OUTPUT)
        print(json.dumps(result, sort_keys=True))
    finally:
        if hasattr(exchange, "close"):
            exchange.close()


if __name__ == "__main__":
    main()
