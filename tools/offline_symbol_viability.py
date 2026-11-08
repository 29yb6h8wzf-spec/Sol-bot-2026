"""Offline symbol viability, using the exact Paper engine risk and cost model."""
from decimal import Decimal as D
from futures_engine.core import Config, plan_trade


def size_for_stop(price, step, min_qty, min_notional, stop_fraction,
                  allocation=D("37.50"), leverage=D("2"), risk_fraction=D("0.01")):
    values = [D(str(x)) for x in (price, step, min_qty, min_notional,
                                 stop_fraction, allocation, leverage, risk_fraction)]
    price, step, min_qty, min_notional, stop_fraction, allocation, leverage, risk_fraction = values
    if any(not v.is_finite() or v <= 0 for v in values):
        raise ValueError("invalid_symbol_sizing_input")
    if leverage > 2 or risk_fraction > D("0.01") or leverage != leverage.to_integral_value():
        raise ValueError("risk_limit_exceeded")
    config = Config(stop_fraction=stop_fraction, leverage=int(leverage),
                    risk_fraction=risk_fraction)
    config.validate()
    risk_budget = allocation * risk_fraction
    cap = allocation * leverage
    try:
        plan = plan_trade(config, "long", price, allocation, allocation,
                          minimum_amount=min_qty, amount_step=step,
                          min_cost=min_notional)
        quantity = D(plan["quantity"])
        rejection = None
        estimated_loss = D(plan["max_estimated_loss"])
    except ValueError as exc:
        if str(exc) != "insufficient balance or dust amount after rounding":
            raise
        # Do not infer a tradable quantity from a rejected plan.
        quantity = D("0")
        rejection = "below_exchange_minimum"
        estimated_loss = D("0")
    notional = quantity * price
    return {
        "quantity": str(quantity),
        "notional": str(notional),
        "stop_risk_before_fees": str(notional * stop_fraction),
        "max_estimated_loss_including_costs": str(estimated_loss),
        "tradable": rejection is None,
        "rejection": rejection,
        "risk_budget": str(risk_budget),
        "leverage_notional_cap": str(cap),
        "round_trip_cost_fraction": str(config.taker_fee * 2 + config.slippage_fraction * 2),
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
