"""Emergency recovery primitive for Binance USDT-M one-way positions.

Flatten and VERIFY exposure is zero BEFORE removing protective orders.
Never run on live funds without independently reviewed integration.
"""
from decimal import Decimal


class RecoveryIncomplete(RuntimeError):
    pass


def _signed_position(exchange, symbol):
    positions = exchange.fetch_positions([symbol])
    total = Decimal("0")
    for p in positions:
        if p.get("symbol") != symbol:
            continue
        qty = Decimal(str(p.get("contracts") or "0"))
        if not qty.is_finite() or qty < 0:
            raise RecoveryIncomplete("invalid_position_quantity")
        side = p.get("side")
        if side not in ("long", "short") and qty:
            raise RecoveryIncomplete("unknown_position_side")
        total += -qty if side == "short" else qty
    return total


def flatten_then_cleanup(exchange, symbol, *, attempts=3):
    """Fail closed. If flatten fails, leave ALL existing protections intact."""
    if attempts < 1 or attempts > 3:
        raise ValueError("invalid_attempt_count")
    last_error = None
    for _ in range(attempts):
        try:
            signed = _signed_position(exchange, symbol)
            if signed:
                exchange.create_order(
                    symbol, "market", "sell" if signed > 0 else "buy",
                    float(abs(signed)), None, {"reduceOnly": True},
                )
            if _signed_position(exchange, symbol) == 0:
                break
        except Exception as exc:
            last_error = exc
    else:
        raise RecoveryIncomplete(
            "position_not_verified_flat_protective_orders_preserved"
        ) from last_error

    # Protection removal is allowed ONLY after exposure is confirmed flat.
    exchange.fapiPrivateDeleteAlgoOpenOrders({"symbol": exchange.market_id(symbol)})
    exchange.cancel_all_orders(symbol)
    if (_signed_position(exchange, symbol) != 0 or
            exchange.fetch_open_orders(symbol)):
        raise RecoveryIncomplete("post_cleanup_reconciliation_failed")
    rows = exchange.fapiPrivateGetOpenAlgoOrders({"symbol": exchange.market_id(symbol)})
    algos = rows.get("orders", []) if isinstance(rows, dict) else rows
    if algos:
        raise RecoveryIncomplete("conditional_orders_still_open")
    return {"status": "FLAT_AND_CLEAN_VERIFIED"}
