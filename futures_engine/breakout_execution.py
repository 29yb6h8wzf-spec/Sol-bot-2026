"""Recompute a fresh SOL/XRP breakout from public candles before protected execution."""
from dataclasses import dataclass
from decimal import Decimal as D
import time

from futures_engine.live import LiveSafetyError, _execute_protected_entry, _validate_trade_risk
from signals_v3.breakout_scan import latest_decision, scan


@dataclass(frozen=True)
class BreakoutIntent:
    symbol: str
    direction: str
    entry: D
    stop: D
    target: D
    quantity: D
    signal_id: str


def route_breakout(exchange, symbol, decision, *, journal, account):
    """Account snapshot and persistent journal are supplied by the execution service."""
    now = time.time_ns() // 1_000_000
    if symbol not in ("SOLUSDT", "XRPUSDT"):
        raise LiveSafetyError("unsupported breakout symbol")
    if decision != latest_decision(now) or not 0 <= now - decision < 60_000:
        raise LiveSafetyError("expired breakout decision")
    event = scan(symbol, decision)
    if event["status"] != "research_candidate":
        return {"status": event["status"]}
    side = event["direction"]
    if side not in ("LONG", "SHORT"):
        raise LiveSafetyError("invalid breakout side")
    pair = symbol[:-4] + "/USDT:USDT"
    stop, target = (D(str(event[k])) for k in ("stop_reference", "target_reference"))
    quote = exchange.fetch_order_book(pair, limit=5)
    levels = quote["asks" if side == "LONG" else "bids"]
    entry = D(str(levels[0][0]))
    reference = D(str(event["entry_reference"]))
    if not entry.is_finite() or entry <= 0 or abs(entry / reference - 1) > D("0.0005"):
        raise LiveSafetyError("entry moved beyond slippage budget")
    capital = min(D(str(account["equity"])), D("150"))
    allocation = capital / 2
    fee = D(str(account.get("fee_rate", "0.0006")))
    slip = D(str(account.get("slippage_rate", "0.0005")))
    if not (fee.is_finite() and slip.is_finite() and fee >= 0 and slip >= 0):
        raise LiveSafetyError("invalid execution costs")
    unit_loss = abs(entry - stop) + (entry + stop) * (fee + slip)
    size = min(allocation * 2 / entry, allocation * D("0.01") / unit_loss)
    qty = D(exchange.amount_to_precision(pair, str(size)))
    if qty <= 0 or qty > size:
        raise LiveSafetyError("size outside allocation")
    intent = BreakoutIntent(pair, side.lower(), entry, stop, target, qty,
                            f"vb-{symbol}-{decision}")
    def validate(plan, **snapshot):
        age = time.time_ns() // 1_000_000 - decision
        if not 0 <= age < 60_000:
            raise LiveSafetyError("expired breakout decision")
        return _validate_trade_risk(plan, **snapshot)
    return _execute_protected_entry(exchange, intent, journal=journal, account=account,
                                    validate=validate)
