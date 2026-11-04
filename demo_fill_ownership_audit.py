"""Read-only classification of Binance DEMO fills against trusted registry.

Never infers ownership from symbol, price or timestamp. Never places orders.
"""
from collections import Counter


def classify_fills(fills, trusted_orders):
    """trusted_orders maps (symbol, order_id) to verified registry receipts."""
    if not isinstance(fills, list) or not isinstance(trusted_orders, dict):
        raise ValueError("invalid_audit_inputs")
    results = []
    seen = set()
    for fill in fills:
        if not isinstance(fill, dict):
            raise ValueError("invalid_fill")
        symbol, order_id, trade_id = (fill.get(k) for k in ("symbol", "order_id", "trade_id"))
        if not all(isinstance(x, str) and x for x in (symbol, order_id, trade_id)):
            raise ValueError("missing_fill_identity")
        key = (symbol, trade_id)
        if key in seen:
            raise ValueError("duplicate_trade_identity")
        seen.add(key)
        receipt = trusted_orders.get((symbol, order_id))
        if receipt is not None:
            if receipt.get("symbol") != symbol or receipt.get("order_id") != order_id:
                raise ValueError("inconsistent_registry_receipt")
            category = "SIGNALPILOT_VERIFIED"
        else:
            # Unmatched is NOT the same as proven external ownership.
            category = "UNATTRIBUTED"
        results.append({"symbol": symbol, "order_id": order_id,
                        "trade_id": trade_id, "category": category})
    counts = Counter(item["category"] for item in results)
    return {"status": "AUDIT_ONLY_NOT_EXECUTABLE",
            "counts": {"SIGNALPILOT_VERIFIED": counts["SIGNALPILOT_VERIFIED"],
                       "UNATTRIBUTED": counts["UNATTRIBUTED"]},
            "fills": results, "execution_authorized": False,
            "orders_sent": False}
