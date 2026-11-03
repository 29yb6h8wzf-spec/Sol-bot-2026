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
    if not intent.signal_id or len(intent.signal_id) > 32 or not all(c.isalnum() or c in "-_" for c in intent.signal_id):
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
    existing_algos = exchange.fapiPrivateGetOpenAlgoOrders({"symbol": exchange.market_id(intent.symbol)})
    existing_rows = existing_algos.get("orders", []) if isinstance(existing_algos, dict) else existing_algos
    if existing_rows:
        raise LiveSafetyError("existing conditional algo orders: reconcile manually")
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
    """Execute with exchange-native protective orders or emergency flatten.

    IMPORTANT: This is NOT atomic. Exchange-specific conditional order API,
    position mode, partial fills and recovery must pass real testnet certification.
    A failure can exceed the planned loss. Keep disabled until certified.
    """
    require_live_arming()
    if os.getenv("BINANCE_BRACKET_CERTIFIED") != "YES_TESTNET_VERIFIED":
        raise LiveSafetyError("native Binance conditional orders not testnet certified")
    if not journal.claim(intent.signal_id):
        raise LiveSafetyError("duplicate signal")
    entry_order = None
    entry_side = "buy" if intent.direction == "long" else "sell"
    exit_side = "sell" if entry_side == "buy" else "buy"
    try:
        validate_intent(intent, **account)
        check_exchange_state(exchange, intent)
        # One-way position mode required for reduceOnly; reject hedge mode.
        mode = exchange.fetch_position_mode(intent.symbol)
        if mode.get("hedged") is not False:
            raise LiveSafetyError("one-way mode required")
        exchange.set_leverage(2, intent.symbol)
        journal.mark(intent.signal_id, "ENTRY_SUBMITTING")
        entry_order = exchange.create_order(
            intent.symbol, "market", entry_side, float(intent.quantity),
            None, {"newClientOrderId": intent.signal_id})
        journal.mark(intent.signal_id, "ENTRY_ACKNOWLEDGED")
        # Reconcile actual filled quantity, not requested quantity.
        positions = exchange.fetch_positions([intent.symbol])
        filled = sum((D(str(p.get("contracts") or 0)) for p in positions
                      if p.get("symbol") == intent.symbol), D("0"))
        if filled <= 0 or filled > intent.quantity:
            raise LiveSafetyError("unexpected filled position; emergency reconciliation")
        journal.mark(intent.signal_id, "PROTECTIVE_ORDERS_SUBMITTING")
        # Binance USD-M conditional orders use /fapi/v1/algoOrder.
        # Do not use legacy create_order STOP_MARKET here.
        symbol_id = exchange.market_id(intent.symbol)
        def submit_algo(kind, trigger, suffix):
            return exchange.fapiPrivatePostAlgoOrder({
                "algoType": "CONDITIONAL", "symbol": symbol_id,
                "side": exit_side.upper(), "type": kind,
                "triggerPrice": exchange.price_to_precision(intent.symbol, str(trigger)),
                "closePosition": "true", "workingType": "MARK_PRICE",
                "clientAlgoId": intent.signal_id + suffix,
            })
        stop_order = submit_algo("STOP_MARKET", intent.stop, "-SL")
        target_order = submit_algo("TAKE_PROFIT_MARKET", intent.target, "-TP")
        journal.mark(intent.signal_id, "BRACKET_ACKNOWLEDGED")
        # Algo orders are separate from ordinary open orders.
        open_algos = exchange.fapiPrivateGetOpenAlgoOrders({"symbol": symbol_id})
        rows = open_algos.get("orders", []) if isinstance(open_algos, dict) else open_algos
        ids = {str(o.get("algoId")) for o in rows}
        if str(stop_order.get("algoId")) not in ids or str(target_order.get("algoId")) not in ids:
            raise LiveSafetyError("protective algo orders not verified active")
        journal.mark(intent.signal_id, "PROTECTED")
        return {"entry": entry_order, "stop": stop_order, "target": target_order}
    except Exception as exc:
        journal.mark(intent.signal_id, "EMERGENCY_FLATTEN_REQUIRED")
        if entry_order is not None:
            try:
                # Cancel protective orders and reduce only the actual open exposure.
                exchange.fapiPrivateDeleteAlgoOpenOrders({"symbol": exchange.market_id(intent.symbol)})
                exchange.cancel_all_orders(intent.symbol)
                positions = exchange.fetch_positions([intent.symbol])
                amount = sum((D(str(p.get("contracts") or 0)) for p in positions
                              if p.get("symbol") == intent.symbol), D("0"))
                if amount > 0:
                    exchange.create_order(intent.symbol, "market", exit_side,
                                          float(amount), None, {"reduceOnly": True})
                # A successful reduce-only submission is not proof of a flat account.
                # Fail closed until the exchange confirms no remaining exposure.
                remaining_positions = exchange.fetch_positions([intent.symbol])
                remaining = sum((abs(D(str(p.get("contracts") or 0)))
                                 for p in remaining_positions
                                 if p.get("symbol") == intent.symbol), D("0"))
                if remaining != 0:
                    raise LiveSafetyError("emergency flatten not confirmed: residual position")
                remaining_algos = exchange.fapiPrivateGetOpenAlgoOrders(
                    {"symbol": exchange.market_id(intent.symbol)})
                algo_rows = (remaining_algos.get("orders", [])
                             if isinstance(remaining_algos, dict) else remaining_algos)
                if algo_rows or exchange.fetch_open_orders(intent.symbol):
                    raise LiveSafetyError("emergency cleanup not confirmed: open orders")
                journal.mark(intent.signal_id, "EMERGENCY_FLATTEN_VERIFIED_FLAT")
            except Exception as flatten_exc:
                journal.mark(intent.signal_id, "CRITICAL_UNPROTECTED_POSITION_MANUAL_INTERVENTION")
                raise LiveSafetyError("emergency flatten failed; manual intervention required") from flatten_exc
        raise LiveSafetyError("entry/bracket lifecycle failed; inspect exchange state") from exc
