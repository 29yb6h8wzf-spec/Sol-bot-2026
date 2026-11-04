"""Read-only, fail-closed historical Demo fill ownership report.

This is evidence only. It NEVER approves risk, allocates capital, or sends orders.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from demo_account_observer import assert_demo
from demo_trade_attribution import SYMBOLS, registry_orders


def _amount(value):
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("invalid_money") from None
    if not n.is_finite():
        raise ValueError("nonfinite_money")
    return n


def report(exchange, day, *, registry_path=None, limit=1000):
    assert_demo(exchange)
    start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    since = int(start.timestamp() * 1000)
    until = int((start + timedelta(days=1)).timestamp() * 1000)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise ValueError("invalid_limit")
    orders, registry_present = registry_orders(registry_path) if registry_path is not None else registry_orders()
    grouped = defaultdict(list)
    seen = set()
    for symbol in SYMBOLS:
        assert_demo(exchange)
        batch = exchange.fetch_my_trades(symbol, since=since, limit=limit)
        if not isinstance(batch, list) or len(batch) >= limit:
            raise ValueError("incomplete_historical_page")
        for fill in batch:
            if not isinstance(fill, dict) or fill.get("symbol") != symbol:
                raise ValueError("invalid_fill")
            timestamp = fill.get("timestamp")
            if type(timestamp) is not int or timestamp < since:
                raise ValueError("invalid_timestamp")
            if timestamp >= until:
                continue
            trade_id, order_id = fill.get("id"), fill.get("order")
            if (not isinstance(trade_id, (int, str)) or not str(trade_id).isdecimal()
                    or not isinstance(order_id, (int, str)) or not str(order_id).isdecimal()):
                raise ValueError("invalid_fill_identity")
            key = (symbol, str(trade_id))
            if key in seen:
                raise ValueError("duplicate_fill")
            seen.add(key)
            fee = fill.get("fee")
            if not isinstance(fee, dict) or fee.get("currency") != "USDT":
                raise ValueError("unreconciled_fee_currency")
            commission = _amount(fee.get("cost"))
            if commission < 0:
                raise ValueError("negative_commission")
            info = fill.get("info")
            if not isinstance(info, dict) or "realizedPnl" not in info:
                raise ValueError("missing_realized_pnl")
            grouped[(symbol, str(order_id))].append((_amount(info["realizedPnl"]), commission))
    rows = []
    for (symbol, order_id), fills in sorted(grouped.items()):
        assert_demo(exchange)
        order = exchange.fetch_order(order_id, symbol)
        if not isinstance(order, dict) or str(order.get("id")) != order_id or order.get("symbol") != symbol:
            raise ValueError("exchange_order_mismatch")
        client_id = order.get("clientOrderId")
        trusted = orders.get((symbol, order_id))
        owned = bool(trusted and isinstance(client_id, str)
                     and client_id == trusted.get("client_order_id")
                     and client_id.startswith("SPDEMO-"))
        rows.append({
            "symbol": symbol,
            "fill_count": len(fills),
            "ownership": "SIGNALPILOT_CONFIRMED" if owned else "UNATTRIBUTED",
            "realized_pnl_usdt": str(sum((p for p, _ in fills), Decimal(0))),
            "commission_usdt": str(sum((f for _, f in fills), Decimal(0))),
        })
    return {
        "day": day,
        "scope": "four_symbols_only",
        "registry_present": registry_present,
        "total_fills": sum(row["fill_count"] for row in rows),
        "unattributed_fills": sum(row["fill_count"] for row in rows if row["ownership"] == "UNATTRIBUTED"),
        "orders": rows,
        "complete_account_coverage": False,
        "allocation_ledger_reconciled": False,
        "execution_authorized": False,
        "orders_sent": False,
        "status": "HISTORICAL_ATTRIBUTION_EVIDENCE_ONLY",
    }
