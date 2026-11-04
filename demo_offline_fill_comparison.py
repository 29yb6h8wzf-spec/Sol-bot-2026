"""Conservative offline comparison of DEMO fills to an independently trusted registry.

This function never claims account-wide reconciliation or permits trading.
"""
from collections import Counter


def classify_fills(fills, trusted_orders):
    if not isinstance(fills, list) or not isinstance(trusted_orders, dict):
        raise ValueError("invalid_inputs")
    results = []
    seen = set()
    for fill in fills:
        if not isinstance(fill, dict):
            raise ValueError("invalid_fill")
        symbol, trade_id, order_id = (fill.get(k) for k in ("symbol", "trade_id", "order_id"))
        client_id = fill.get("client_order_id")
        if not all(isinstance(v, str) and v for v in (symbol, trade_id, order_id, client_id)):
            raise ValueError("missing_fill_identity")
        key = (symbol, trade_id)
        if key in seen:
            raise ValueError("duplicate_fill")
        seen.add(key)
        trusted = trusted_orders.get((symbol, order_id))
        if trusted is not None and (not isinstance(trusted, str) or not trusted):
            raise ValueError("invalid_trusted_order")
        matched = trusted is not None and trusted == client_id
        results.append({"symbol": symbol, "trade_id": trade_id, "order_id": order_id,
                        "classification": "MATCHED_TRUSTED_REGISTRY" if matched else "UNATTRIBUTED"})
    counts = Counter(row["classification"] for row in results)
    return {"status": "AUDIT_ONLY_NOT_EXECUTABLE",
            "total_fills": len(results),
            "matched_fills": counts["MATCHED_TRUSTED_REGISTRY"],
            "unattributed_fills": counts["UNATTRIBUTED"],
            "unique_orders": len({(r["symbol"], r["order_id"]) for r in results}),
            "fills": results,
            "account_reconciled": False,
            "execution_authorized": False,
            "orders_sent": False}
