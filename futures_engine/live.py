"""Fail-closed Binance USDT-M live execution primitives.

Not wired to the paper scanner. Caller must provide an independently verified
85+ score and an exchange-validated plan. Never auto-enable from deployment.
"""
from dataclasses import dataclass
from decimal import Decimal as D
import os

ALLOWED = frozenset({"BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT"})


class LiveSafetyError(RuntimeError):
    pass


@dataclass(frozen=True)
class TradeIntent:
    symbol: str
    direction: str
    score: int
    source: str
    entry: D
    stop: D
    target: D
    quantity: D
    signal_id: str


def validate_intent(intent, *, equity, day_start_equity, existing_risk=D("0"),
                    used_margin=D("0"), fee_rate=D("0.0006"),
                    slippage_rate=D("0.0005")):
    """Offline guard; conservative estimated loss, not guaranteed maximum."""
    if intent.symbol not in ALLOWED:
        raise LiveSafetyError("symbol not allowed")
    if intent.direction not in ("long", "short"):
        raise LiveSafetyError("invalid direction")
    if intent.source != "verified_85_score_engine" or not isinstance(intent.score, int) or intent.score < 85 or intent.score > 100:
        raise LiveSafetyError("unverified signal quality")
    if not intent.signal_id or len(intent.signal_id) > 64 or not all(c.isalnum() or c in "-_" for c in intent.signal_id):
        raise LiveSafetyError("invalid idempotency key")
    entry, stop, target, qty = map(D, (intent.entry, intent.stop, intent.target, intent.quantity))
    equity, day_start_equity, existing_risk, used_margin = map(D, (equity, day_start_equity, existing_risk, used_margin))
    if not all(x.is_finite() for x in (entry, stop, target, qty, equity, day_start_equity, existing_risk, used_margin)):
        raise LiveSafetyError("nonfinite input")
    if min(entry, stop, target, qty, equity, day_start_equity) <= 0 or min(existing_risk, used_margin) < 0:
        raise LiveSafetyError("invalid numeric input")
    if (intent.direction == "long" and not stop < entry < target) or (intent.direction == "short" and not target < entry < stop):
        raise LiveSafetyError("invalid protective bracket")
    notional = entry * qty
    if notional > equity * D("2") or used_margin + notional / D("2") > equity:
        raise LiveSafetyError("2x margin cap")
    estimated_loss = qty * (abs(entry - stop) + (entry + stop) * (D(fee_rate) + D(slippage_rate)))
    if estimated_loss > D("1.50"):
        raise LiveSafetyError("$1.50 risk limit")
    remaining = min(D("7.50"), day_start_equity * D("0.05")) - max(D("0"), day_start_equity - equity)
    if remaining <= 0 or existing_risk + estimated_loss > remaining:
        raise LiveSafetyError("portfolio daily risk budget exceeded")
    return {"notional": notional, "estimated_loss": estimated_loss, "margin": notional / D("2")}


def require_live_arming():
    """Explicit, separate runtime switch. Never infer consent from credentials."""
    if os.getenv("TRADING_MODE") != "live" or os.getenv("SIGNALPILOT_LIVE_ARMED") != "YES_I_ACCEPT_REAL_LOSSES":
        raise LiveSafetyError("live trading disarmed")


def create_binance_client(api_key, api_secret):
    """Authenticated client construction; no network calls or orders."""
    import ccxt
    if not api_key or not api_secret:
        raise LiveSafetyError("missing credentials")
    return ccxt.binanceusdm({
        "apiKey": api_key, "secret": api_secret,
        "enableRateLimit": True, "timeout": 15000,
        "options": {"defaultType": "future"},
    })


def check_exchange_state(exchange, intent):
    """Read-only exchange reconciliation. Reject any existing exposure/orders."""
    if not exchange.check_required_credentials():
        raise LiveSafetyError("exchange credentials unavailable")
    positions = exchange.fetch_positions([intent.symbol])
    if any(abs(D(str(p.get("contracts") or 0))) > 0 for p in positions):
        raise LiveSafetyError("existing position: reconcile manually")
    if exchange.fetch_open_orders(intent.symbol):
        raise LiveSafetyError("existing open orders: reconcile manually")
    market = exchange.market(intent.symbol)
    if not market.get("linear") or not market.get("swap") or market.get("active") is False:
        raise LiveSafetyError("market not active USDT-M perpetual")
    precision_qty = D(str(exchange.amount_to_precision(intent.symbol, str(intent.quantity))))
    if precision_qty != intent.quantity:
        raise LiveSafetyError("quantity not aligned to exchange precision")
    minimum = D(str((market.get("limits", {}).get("amount") or {}).get("min") or 0))
    minimum_cost = D(str((market.get("limits", {}).get("cost") or {}).get("min") or 0))
    if precision_qty < minimum or precision_qty * intent.entry < minimum_cost:
        raise LiveSafetyError("below exchange minimum")


def execute_protected_entry(exchange, intent, *, journal, account):
    """Never place unprotected market entries.

    Caller supplies durable journal with claim(signal_id) -> bool and
    mark(signal_id, state) methods. Native conditional orders are exchange
    version/position-mode dependent: fail closed until separately certified.
    """
    require_live_arming()
    if not journal.claim(intent.signal_id):
        raise LiveSafetyError("duplicate signal")
    try:
        validate_intent(intent, **account)
        check_exchange_state(exchange, intent)
        journal.mark(intent.signal_id, "BLOCKED_PENDING_NATIVE_BRACKET_CERTIFICATION")
        raise LiveSafetyError("native stop/target atomic lifecycle not certified; no live order sent")
    except Exception:
        journal.mark(intent.signal_id, "REQUIRES_REVIEW")
        raise
