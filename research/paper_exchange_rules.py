"""Pinned, read-only Binance USDT-M exchange filter snapshot.

Observed from the public Binance exchangeInfo connector on 2026-11-09.
Research/Paper validation ONLY; refresh from current exchangeInfo before any
real trading. Never assume a historical snapshot authorizes a live order.
"""
from decimal import Decimal

_RULES = {
    "SOL/USDT:USDT": {
        "step_size": "0.01", "min_qty": "0.01",
        "max_qty": "80000", "min_notional": "5", "tick_size": "0.0100",
    },
    "XRP/USDT:USDT": {
        "step_size": "0.1", "min_qty": "0.1",
        "max_qty": "2000000", "min_notional": "5", "tick_size": "0.0001",
    },
}


def research_exchange_rules(symbol):
    if symbol not in _RULES:
        raise ValueError("missing pinned Binance Futures exchange rules")
    return dict(_RULES[symbol])


def check_paper_exchange_plan(symbol, plan):
    rules = research_exchange_rules(symbol)
    qty = Decimal(str(plan["quantity"]))
    entry = Decimal(str(plan["entry_mid"]))
    stop = Decimal(str(plan["stop"]))
    target = Decimal(str(plan["target"]))
    step = Decimal(rules["step_size"])
    tick = Decimal(rules["tick_size"])
    if not all(v.is_finite() and v > 0 for v in (qty, entry, stop, target)):
        raise ValueError("invalid paper exchange plan values")
    if (qty < Decimal(rules["min_qty"])
            or qty > Decimal(rules["max_qty"])
            or qty % step != 0):
        raise ValueError("paper quantity violates exchange filters")
    if stop % tick or target % tick:
        raise ValueError("paper stop/target violates exchange tick")
    if qty * entry < Decimal(rules["min_notional"]):
        raise ValueError("paper order below Binance min notional")
    return True
