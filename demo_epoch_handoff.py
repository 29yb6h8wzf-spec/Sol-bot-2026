"""Connect independently verified signals to the reconciled Demo epoch gate.

GET-only: Binance account/market checks, ATR bracket planning, portfolio risk,
and exactly-once reservation for a separate supervised Demo executor.
This is NOT an order-submission module. Never import real trading clients.
"""
import time
from datetime import datetime, timezone
from decimal import Decimal
from demo_account_snapshot import read_snapshot
from demo_execution_gate import validate, reserve, DemoGateBlocked
from demo_independent_verifier import verify
from demo_order_planner import plan as plan_bracket
from demo_risk_adapter import preflight_with_epoch

MARKETS = {"SOL/USDT:USDT": "SOLUSDT", "XRP/USDT:USDT": "XRPUSDT"}
AUDIT_ROOT = "/opt/signalpilot-audit-worktree"


def epoch_paths(now=None):
    now = int(time.time()) if now is None else int(now)
    day = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
    return (f"{AUDIT_ROOT}/demo-epoch-baseline-{day}.json",
            f"{AUDIT_ROOT}/demo-epoch-risk-status-{day}.json")


def market_filters(exchange, symbol):
    """Use exchange-reported tick, lot and minimum notional, not user data."""
    markets = exchange.fapiPublicGetExchangeInfo()
    rows = [row for row in markets.get("symbols", [])
            if row.get("symbol") == MARKETs(symbol)]
    if len(rows) != 1 or rows[0].get("status") != "TRADING":
        raise DemoGateBlocked("market_filters_missing")
    filters = {f.get("filterType"): f for f in rows[0].get("filters", [])}
    tick = filters.get("PRICE_FILTER", {}).get("tickSize")
    lot = filters.get("LOT_SIZE", {})
    step = lot.get("stepSize")
    min_qty = lot.get("minQty")
    notional = filters.get("MIN_NOTIONAL", {}).get("notional")
    if any(x is None for x in (tick, step, min_qty, notional)):
        raise DemoGateBlocked("incomplete_exchange_filters")
    if any(Decimal(str(x)) <= 0 for x in (tick, step, min_qty, notional)):
        raise DemoGateBlocked("invalid_exchange_filters")
    return tick, step, min_qty, notional


def MARKETs(symbol):
    if symbol not in MARKETS:
        raise DemoGateBlocked("unsupported_demo_symbol")
    return MARKETS[symbol]


def closed_bars(exchange, symbol, candle):
    raw = exchange.fetch_ohlcv(symbol, timeframe="5m", limit=120)
    if not isinstance(raw, list) or len(raw) < 17:
        raise DemoGateBlocked("insufficient_market_bars")
    # Only closed bars; never include an in-progress candle.
    bars = [b for b in raw if isinstance(b, (list, tuple))
            and len(b) >= 6 and type(b[0]) is int and b[0] <= candle]
    if len(bars) < 16 or bars[-1][0] != candle:
        raise DemoGateBlocked("independent_candle_mismatch")
    return bars


def prepare(payload, exchange, *, baseline_path=None, status_path=None,
            now=None, verifier=verify):
    """Return trusted, risk-approved offline handoff. No orders or reservations."""
    now = int(time.time()) if now is None else int(now)
    defaults = epoch_paths(now)
    baseline_path = defaults[0] if baseline_path is None else baseline_path
    status_path = defaults[1] if status_path is None else status_path
    if not isinstance(payload, dict) or type(payload.get("timestamp")) is not int:
        raise DemoGateBlocked("invalid_signal_payload")
    if not getattr(exchange, "_signalpilot_get_only_guard", False):
        raise DemoGateBlocked("demo_get_only_guard_missing")
    # Verifier independently recomputes candidate from exchange market data.
    verified = verifier(payload)
    if not isinstance(verified, dict):
        raise DemoGateBlocked("independent_verification_failed")
    symbol = verified.get("symbol")
    raw = MARKETs(symbol)
    candle = verified.get("closed_5m_candle_ms")
    if type(candle) is not int:
        raise DemoGateBlocked("verified_candle_missing")
    account = read_snapshot(exchange, raw, now=now)
    bars = closed_bars(exchange, symbol, candle)
    tick, step, min_qty, min_cost = market_filters(exchange, symbol)
    planned = plan_bracket(verified, bars, tick=tick, step=step,
                           min_qty=min_qty, min_cost=min_cost,
                           now_ms=now * 1000, capital="150", leverage=2,
                           max_risk="1.50")
    route = {"signal_id": payload["signal_id"],
             "status": "DEMO_ELIGIBLE_NOT_SUBMITTED"}
    intent = validate(payload, verified, route, planned, account, now=now)
    checked = dict(planned)
    checked["source"] = verified["source"]
    checked["score"] = verified["score"]
    ok, reason = preflight_with_epoch(checked, baseline_path=baseline_path,
                                      status_path=status_path, now=now)
    if not ok:
        raise DemoGateBlocked("epoch_risk_blocked:" + str(reason))
    return {"signal": payload, "verified": verified, "route": route,
            "plan": planned, "account": account, "intent": intent,
            "epoch_risk": "RECONCILED_OFFLINE", "orders_sent": False}


def reserve_handoff(db_path, handoff, *, now=None):
    """Reserve only after fresh revalidation by caller; no exchange order."""
    if not isinstance(handoff, dict) or handoff.get("epoch_risk") != "RECONCILED_OFFLINE":
        raise DemoGateBlocked("untrusted_handoff")
    return reserve(db_path, handoff["signal"], handoff["verified"],
                   handoff["route"], handoff["plan"], handoff["account"], now=now)
