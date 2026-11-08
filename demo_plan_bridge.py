"""Signal -> independent verification -> indicative Binance Futures plan.

READ ONLY. Never imports authenticated exchange clients, never submits orders.
No plan produced here authorizes demo or live execution.
"""
import json
import sqlite3
import time
from decimal import Decimal as D, ROUND_DOWN
from pathlib import Path

from demo_independent_verifier import verify
from demo_order_planner import plan
from futures_engine.market import closed_futures_bars

FEE_AND_SLIPPAGE_BUFFER = D("0.002")  # Minimum reserve relative to entry notional.
ASSUMED_TAKER_FEE = D("0.0006")
ASSUMED_SLIPPAGE = D("0.0005")
SYMBOLS = frozenset(("BTC/USDT:USDT", "ETH/USDT:USDT",
                     "SOL/USDT:USDT", "XRP/USDT:USDT"))


def exchange_filters(market):
    if not isinstance(market, dict) or not market.get("swap") or not market.get("linear"):
        raise ValueError("not_linear_futures")
    filters = market.get("info", {}).get("filters")
    if not isinstance(filters, list):
        raise ValueError("exchange_filters_missing")
    by_name = {f.get("filterType"): f for f in filters if isinstance(f, dict)}
    try:
        tick = D(str(by_name["PRICE_FILTER"]["tickSize"]))
        lot = by_name["MARKET_LOT_SIZE"]
        step = D(str(lot["stepSize"]))
        min_qty = D(str(lot["minQty"]))
        min_cost = D(str(by_name["MIN_NOTIONAL"]["notional"]))
    except (KeyError, TypeError, ValueError):
        raise ValueError("exchange_filters_missing") from None
    if any(not v.is_finite() for v in (tick, step, min_qty, min_cost)):
        raise ValueError("nonfinite_exchange_filters")
    if min(tick, step, min_qty, min_cost) <= 0:
        raise ValueError("invalid_exchange_filters")
    return dict(tick=tick, step=step, min_qty=min_qty, min_cost=min_cost)


def _verified_plan(payload, verifier, loader, now_ms):
    now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
    if not isinstance(payload, dict) or type(payload.get("timestamp")) is not int:
        raise ValueError("invalid_signal")
    if not 0 <= now_ms - payload["timestamp"] * 1000 <= 120000:
        raise ValueError("signal_stale_or_future")
    verified = verifier(payload, now=now_ms // 1000)
    if verified.get("symbol") not in SYMBOLS:
        raise ValueError("unverified_symbol")
    exchange, market, bars = loader(verified["symbol"], "5m")
    try:
        if market.get("symbol") != verified["symbol"]:
            raise ValueError("market_symbol_mismatch")
        filters = exchange_filters(market)
        result = plan(verified, bars, now_ms=now_ms, **filters)
    finally:
        if hasattr(exchange, "close"):
            exchange.close()
    # Model the same adverse entry and stop fills as the offline risk check.
    # The next open can gap, so execution still requires a fresh risk check.
    entry, stop = D(result["entry"]), D(result["stop"])
    direction = 1 if result["side"] == "long" else -1
    entry_fill = entry * (1 + direction * ASSUMED_SLIPPAGE)
    stop_fill = stop * (1 - direction * ASSUMED_SLIPPAGE)
    distance = abs(entry - stop)
    # Cover fees on both modeled fills and the offline check's stop-level fee.
    fees = ASSUMED_TAKER_FEE * (entry_fill + max(stop, stop_fill))
    stop_loss = abs(entry_fill - stop_fill) + fees
    max_unit_loss = max(stop_loss, distance + entry * FEE_AND_SLIPPAGE_BUFFER)
    max_entry = max(entry, entry_fill)
    step = filters["step"]
    quantity_cap = min(D(result["quantity"]), D("1.50") / max_unit_loss,
                       D("300") / max_entry)
    qty = (quantity_cap / step).to_integral_value(rounding=ROUND_DOWN) * step
    if qty < filters["min_qty"] or qty * min(entry, entry_fill) < filters["min_cost"]:
        raise ValueError("below_exchange_minimum_after_cost_buffer")
    buffered_risk = qty * max_unit_loss
    if buffered_risk > D("1.50") or qty * max_entry > D("300"):
        raise ValueError("buffered_risk_cap_exceeded")
    result["quantity"] = str(qty)
    result["estimated_notional"] = str(qty * entry)
    result["estimated_max_stop_loss_before_fees"] = str(qty * abs(entry - stop))
    result["estimated_loss_including_buffer"] = str(buffered_risk)
    result["fee_slippage_reserve_rate"] = str((max_unit_loss - distance) / entry)
    result["risk_snapshot_approved"] = False
    result["execution_authorized"] = False
    result["orders_sent"] = False
    return verified, result


def build_plan(payload, *, verifier=verify, loader=closed_futures_bars, now_ms=None):
    _, result = _verified_plan(payload, verifier, loader, now_ms)
    return result


def verify_and_plan(payload, *, verifier=verify, loader=closed_futures_bars, now_ms=None):
    """Keep the independently computed event identity for router deduplication."""
    verified, result = _verified_plan(payload, verifier, loader, now_ms)
    return {**verified, **result}


def journal_inbox(inbox_path, journal_path, *, planner=build_plan, now_ms=None):
    now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
    with sqlite3.connect(str(inbox_path)) as inbox:
        rows = inbox.execute(
            "SELECT signal_id,payload FROM signals ORDER BY received_at DESC LIMIT 100").fetchall()
    results = []
    with sqlite3.connect(str(journal_path)) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS demo_plans (
            signal_id TEXT PRIMARY KEY, status TEXT NOT NULL,
            reason TEXT NOT NULL, plan_json TEXT, checked_at INTEGER NOT NULL)""")
        for sid, raw in reversed(rows):
            if not isinstance(sid, str) or not sid or len(sid) > 128:
                continue
            if db.execute("SELECT 1 FROM demo_plans WHERE signal_id=?", (sid,)).fetchone():
                continue
            result = None
            try:
                payload = json.loads(raw)
                if not isinstance(payload, dict) or payload.get("signal_id") != sid:
                    raise ValueError("signal_id_mismatch")
                result = planner(payload, now_ms=now_ms)
                status, reason = "PLANNED_ONLY", "not_authorized_for_execution"
            except (Exception) as exc:
                status, reason = "BLOCKED", str(exc)[:160]
            db.execute("INSERT INTO demo_plans VALUES (?,?,?,?,?)",
                       (sid, status, reason,
                        json.dumps(result, sort_keys=True) if result else None,
                        now_ms // 1000))
            results.append({"signal_id": sid, "status": status,
                            "reason": reason, "orders_sent": False})
    return results


def main():
    for row in journal_inbox("/opt/signalpilot/signal-inbox.sqlite3",
                             "/opt/signalpilot/demo-plan-journal.sqlite3"):
        print(json.dumps(row, sort_keys=True))


if __name__ == "__main__":
    main()
