"""Fail-closed, idempotent handoff from verified SignalPilot plans to DEMO execution.

This module NEVER submits orders. It only reserves a candidate for a separate
Demo-only executor. No production service imports or invokes this module yet.
"""
import json
import sqlite3
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from verified_signal_identity import verified_event_key

SYMBOLS = frozenset({"SOL/USDT:USDT", "XRP/USDT:USDT"})
MAX_LEVERAGE = 2
MAX_MARGIN_FRACTION = Decimal("0.05")
MAX_RISK_USDT = Decimal("1.50")
MAX_DAILY_LOSS_FRACTION = Decimal("0.05")
FEE_SLIPPAGE_RESERVE = Decimal("0.002")
MAX_SIGNAL_AGE_SECONDS = 120
MAX_ACCOUNT_AGE_SECONDS = 10


class DemoGateBlocked(ValueError):
    """Candidate is not safe to hand to the Demo executor."""


def dec(value, name):
    if isinstance(value, bool):
        raise DemoGateBlocked("invalid_" + name)
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise DemoGateBlocked("invalid_" + name) from None
    if not number.is_finite():
        raise DemoGateBlocked("invalid_" + name)
    return number


def validate(signal, verified, route, plan, account, *, now=None):
    """Validate independent verification, risk, and fresh DEMO account state.

    All inputs must come from trusted loaders: verified from the independent
    market-data verifier, account from authenticated Demo GET endpoints.
    Never construct them from the incoming signal payload.
    """
    now = int(time.time()) if now is None else int(now)
    if not all(isinstance(x, dict) for x in (signal, verified, route, plan, account)):
        raise DemoGateBlocked("missing_evidence")
    sid = signal.get("signal_id")
    if not isinstance(sid, str) or not (1 <= len(sid) <= 128):
        raise DemoGateBlocked("invalid_signal_id")
    if verified.get("signal_id") != sid or route.get("signal_id") != sid or plan.get("signal_id") != sid:
        raise DemoGateBlocked("identity_mismatch")
    timestamp = signal.get("timestamp")
    if type(timestamp) is not int or not 0 <= now - timestamp <= MAX_SIGNAL_AGE_SECONDS:
        raise DemoGateBlocked("stale_signal")
    proof = verified.get("verification")
    if (not isinstance(proof, dict) or proof.get("status") != "RECALCULATED_RESEARCH_CANDIDATE"
            or proof.get("score_verified_independently") is not True
            or proof.get("execution_authorized") is not False):
        raise DemoGateBlocked("independent_proof_required")
    if verified.get("source") != "verified_85_score_engine":
        raise DemoGateBlocked("unverified_source")
    score = verified.get("score")
    if type(score) is not int or not 85 <= score <= 100:
        raise DemoGateBlocked("unverified_score")
    symbol = verified.get("symbol")
    side = verified.get("direction")
    if symbol not in SYMBOLS or side not in ("long", "short"):
        raise DemoGateBlocked("unsupported_market_or_side")
    if plan.get("symbol") != symbol or plan.get("side") != side:
        raise DemoGateBlocked("plan_mismatch")
    if route.get("status") != "DEMO_ELIGIBLE_NOT_SUBMITTED":
        raise DemoGateBlocked("router_not_eligible")
    if plan.get("status") != "INDICATIVE_PLAN_ONLY_NOT_EXECUTABLE" or plan.get("orders_sent") is not False:
        raise DemoGateBlocked("plan_not_ready")
    if account.get("endpoint") != "https://demo-fapi.binance.com":
        raise DemoGateBlocked("not_demo_endpoint")
    if account.get("authenticated") is not True or account.get("one_way") is not True:
        raise DemoGateBlocked("account_not_verified")
    observed = account.get("observed_at")
    if type(observed) is not int or not 0 <= now - observed <= MAX_ACCOUNT_AGE_SECONDS:
        raise DemoGateBlocked("stale_account_snapshot")
    if account.get("positions_count") != 0 or account.get("orders_count") != 0 or account.get("algo_orders_count") != 0:
        raise DemoGateBlocked("account_not_flat")
    if account.get("margin_type") != "isolated" or account.get("leverage") != MAX_LEVERAGE:
        raise DemoGateBlocked("demo_configuration_mismatch")
    wallet = dec(account.get("wallet_usdt"), "wallet")
    available = dec(account.get("available_usdt"), "available")
    daily_pnl = dec(account.get("realized_pnl_today_usdt"), "daily_pnl")
    if wallet <= 0 or available <= 0 or daily_pnl <= -wallet * MAX_DAILY_LOSS_FRACTION:
        raise DemoGateBlocked("daily_loss_or_balance_guard")
    qty = dec(plan.get("quantity"), "quantity")
    entry = dec(plan.get("entry"), "entry")
    stop = dec(plan.get("stop"), "stop")
    target = dec(plan.get("target"), "target")
    min_notional = dec(account.get("min_notional_usdt"), "min_notional")
    if min(qty, entry, stop, target, min_notional) <= 0:
        raise DemoGateBlocked("invalid_order_values")
    if side == "long" and not stop < entry < target:
        raise DemoGateBlocked("invalid_long_bracket")
    if side == "short" and not target < entry < stop:
        raise DemoGateBlocked("invalid_short_bracket")
    notional = qty * entry
    if notional < min_notional:
        raise DemoGateBlocked("below_exchange_minimum")
    if notional > wallet * MAX_MARGIN_FRACTION * MAX_LEVERAGE:
        raise DemoGateBlocked("margin_allocation_exceeded")
    if notional / MAX_LEVERAGE > available:
        raise DemoGateBlocked("insufficient_available_margin")
    estimated_loss = qty * (abs(entry - stop) + entry * FEE_SLIPPAGE_RESERVE)
    if estimated_loss > MAX_RISK_USDT:
        raise DemoGateBlocked("trade_risk_exceeded")
    try:
        event_key = verified_event_key(verified)
    except (ValueError, KeyError, TypeError):
        raise DemoGateBlocked("invalid_verified_event_identity") from None
    return {"signal_id": sid, "event_key": event_key, "symbol": symbol, "direction": side,
            "quantity": str(qty), "entry": str(entry), "stop": str(stop),
            "target": str(target), "notional": str(notional),
            "estimated_loss_with_buffer": str(estimated_loss),
            "mode": "DEMO_ONLY", "orders_sent": False}


def reserve(db_path, signal, verified, route, plan, account, *, now=None):
    """Durable exactly-once reservation. UNKNOWN state must be reconciled, not retried."""
    intent = validate(signal, verified, route, plan, account, now=now)
    path = Path(db_path)
    if not path.parent.is_dir():
        raise DemoGateBlocked("journal_directory_missing")
    with sqlite3.connect(str(path), timeout=5, isolation_level=None) as db:
        db.execute("PRAGMA busy_timeout=5000")
        db.execute("""CREATE TABLE IF NOT EXISTS demo_execution_reservations (
            signal_id TEXT PRIMARY KEY, event_key TEXT NOT NULL UNIQUE, state TEXT NOT NULL,
            intent_json TEXT NOT NULL, created_at INTEGER NOT NULL)""")
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT state FROM demo_execution_reservations WHERE signal_id=?",
                              (intent["signal_id"],)).fetchone()
        if existing:
            db.execute("ROLLBACK")
            raise DemoGateBlocked("already_reserved_" + existing[0])
        duplicate_event = db.execute("SELECT signal_id FROM demo_execution_reservations WHERE event_key=?",
                                     (intent["event_key"],)).fetchone()
        if duplicate_event:
            db.execute("ROLLBACK")
            raise DemoGateBlocked("verified_event_already_reserved")
        db.execute("INSERT INTO demo_execution_reservations VALUES (?,?,?,?,?)",
                   (intent["signal_id"], intent["event_key"], "RESERVED_NO_ORDERS",
                    json.dumps(intent, sort_keys=True), int(time.time())))
        db.execute("COMMIT")
    return intent
