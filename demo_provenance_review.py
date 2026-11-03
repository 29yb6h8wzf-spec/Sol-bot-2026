"""Offline-only review of Binance DEMO fill provenance.

Only a verified registry receipt plus independent exchange order read-back
can prove ownership. This module never creates orders or authorizes trading.
"""
from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib


class ReviewError(ValueError):
    pass


def number(value):
    try:
        value = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        raise ReviewError("invalid_amount") from None
    if not value.is_finite():
        raise ReviewError("nonfinite_amount")
    return value


def classify_fills(fills, order_lookups, receipts):
    if not all(isinstance(x, list) for x in (fills, order_lookups, receipts)):
        raise ReviewError("invalid_inputs")
    lookups, trusted = {}, {}
    for row in order_lookups:
        if not isinstance(row, dict):
            raise ReviewError("invalid_lookup")
        key = (row.get("symbol"), str(row.get("order_id")))
        if key in lookups:
            raise ReviewError("duplicate_lookup")
        lookups[key] = row
    clients = set()
    for row in receipts:
        if not isinstance(row, dict):
            raise ReviewError("invalid_receipt")
        symbol, oid, sid, leg = (row.get(k) for k in
                                 ("symbol", "order_id", "signal_id", "leg"))
        if (not isinstance(symbol, str) or not symbol.endswith("/USDT:USDT") or
                not isinstance(oid, str) or not oid.isdecimal() or
                not isinstance(sid, str) or not 1 <= len(sid) <= 128 or
                leg not in ("entry", "stop", "target")):
            raise ReviewError("invalid_receipt_identity")
        client = "SPDEMO-" + hashlib.sha256(
            (sid + ":" + leg).encode()).hexdigest()[:24]
        if row.get("client_order_id") != client:
            raise ReviewError("invalid_receipt_client")
        key = (symbol, oid)
        if key in trusted or client in clients:
            raise ReviewError("duplicate_receipt")
        clients.add(client)
        trusted[key] = row
    groups, ids = {}, set()
    for row in fills:
        if not isinstance(row, dict):
            raise ReviewError("invalid_fill")
        symbol, oid, tid = (row.get(k) for k in ("symbol", "order_id", "trade_id"))
        if (not isinstance(symbol, str) or not symbol.endswith("/USDT:USDT") or
                not isinstance(oid, str) or not oid.isdecimal() or
                not isinstance(tid, str) or not tid.isdecimal()):
            raise ReviewError("invalid_fill_identity")
        if (symbol, tid) in ids:
            raise ReviewError("duplicate_fill")
        ids.add((symbol, tid))
        realized, fee = number(row.get("realized_pnl_usdt")), number(row.get("fee_usdt"))
        if fee < 0:
            raise ReviewError("negative_fee")
        group = groups.setdefault((symbol, oid),
                                  {"count": 0, "realized": Decimal(0), "fees": Decimal(0)})
        group["count"] += 1
        group["realized"] += realized
        group["fees"] += fee
    counts = Counter()
    owned_count, unknown_count = 0, 0
    owned_realized, owned_fees = Decimal(0), Decimal(0)
    rows = []
    for (symbol, oid), group in sorted(groups.items()):
        lookup = lookups.get((symbol, oid))
        receipt = trusted.get((symbol, oid))
        if (not lookup or lookup.get("confirmed") is not True or
                lookup.get("symbol") != symbol or lookup.get("order_id") != oid):
            status = "ORDER_LOOKUP_UNVERIFIED"
        elif not isinstance(lookup.get("client_order_id"), str) or not lookup["client_order_id"]:
            status = "MISSING_CLIENT_ORDER_ID"
        elif receipt is not None:
            status = ("VERIFIED_SIGNALPILOT" if
                      receipt["client_order_id"] == lookup["client_order_id"]
                      else "REGISTRY_EXCHANGE_MISMATCH")
        elif lookup["client_order_id"].startswith("SPDEMO-"):
            status = "UNREGISTERED_SPDEMO_TAG"
        else:
            status = "EXTERNAL_OR_UNTAGGED"
        counts[status] += 1
        owned = status == "VERIFIED_SIGNALPILOT"
        if owned:
            owned_count += group["count"]
            owned_realized += group["realized"]
            owned_fees += group["fees"]
        else:
            unknown_count += group["count"]
        rows.append({
            "order_fingerprint": hashlib.sha256(
                (symbol + ":" + oid).encode()).hexdigest()[:16],
            "symbol": symbol, "fill_count": group["count"],
            "classification": status, "ownership_proven": owned,
        })
    return {
        "source": "signalpilot_offline_demo_provenance_review",
        "status": "AUDIT_ONLY_NOT_EXECUTABLE",
        "total_fills": len(fills), "unique_orders": len(groups),
        "verified_signalpilot_fills": owned_count,
        "unattributed_fills": unknown_count,
        "verified_realized_pnl_usdt": str(owned_realized),
        "verified_commissions_usdt": str(owned_fees),
        "order_classifications": dict(sorted(counts.items())),
        "orders": rows,
        "allocation_ledger_reconciled": False,
        "execution_authorized": False, "orders_sent": False,
    }
