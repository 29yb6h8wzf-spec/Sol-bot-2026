"""Read-only offline symbol viability with strict downward LOT_SIZE rounding.

Inputs are an explicitly dated public exchangeInfo snapshot and a separate
dated price snapshot. This module does not contact an exchange or place orders.
"""
from decimal import Decimal as D, ROUND_DOWN


def size_for_stop(price, step, min_qty, min_notional, stop_fraction,
                  allocation=D("37.50"), leverage=D("2"), risk_fraction=D("0.01")):
    values = [D(str(x)) for x in (price, step, min_qty, min_notional, stop_fraction,
                                 allocation, leverage, risk_fraction)]
    price, step, min_qty, min_notional, stop_fraction, allocation, leverage, risk_fraction = values
    if any(not v.is_finite() or v <= 0 for v in values):
        raise ValueError("invalid_symbol_sizing_input")
    if leverage > 2 or risk_fraction > D("0.01"):
        raise ValueError("risk_limit_exceeded")
    risk_budget = allocation * risk_fraction
    leverage_notional_cap = allocation * leverage
    raw_quantity = min(risk_budget / (price * stop_fraction), leverage_notional_cap / price)
    quantity = (raw_quantity / step).to_integral_value(rounding=ROUND_DOWN) * step
    notional = quantity * price
    tradable = quantity >= min_qty and notional >= min_notional
    return {
        "quantity": str(quantity),
        "notional": str(notional),
        "stop_risk_before_fees": str(notional * stop_fraction),
        "tradable": tradable,
        "rejection": None if tradable else "below_exchange_minimum",
        "risk_budget": str(risk_budget),
        "leverage_notional_cap": str(leverage_notional_cap),
    }


def symbol_report(snapshot):
    results = {}
    for symbol, data in snapshot["symbols"].items():
        results[symbol] = {
            str(stop): size_for_stop(data["price"], data["stepSize"],
                                      data["minQty"], data["minNotional"], stop)
            for stop in ("0.003", "0.005", "0.01", "0.02")
        }
    return results
