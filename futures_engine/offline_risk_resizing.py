"""Pure research sizing for non-executable, archived paper candidates.

No exchange, network, key, broker or persistence imports. A returned quantity is
a hypothetical research input, NOT permission to execute an order. The current
Paper engine has four 37.50-USDT ledgers, not one interchangeable 150-USDT ledger.
"""
from decimal import Decimal, InvalidOperation, ROUND_DOWN


def _decimal(value, name):
    if isinstance(value, bool):
        raise ValueError("invalid_" + name)
    try:
        number = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise ValueError("invalid_" + name) from exc
    if not number.is_finite():
        raise ValueError("invalid_" + name)
    return number


def research_resize(
    plan, *, next_candle_open, amount_step, min_amount, min_notional,
    paper_equity="37.50", day_start_equity="37.50",
    available_margin="37.50", portfolio_equity="150",
    portfolio_day_start_equity="150", portfolio_open_risk="0",
    fee_rate="0.0006", slippage_rate="0.0005",
):
    """Conservatively reduce a research candidate using next-bar fill assumptions.

    Uses the EXISTING 1% per-symbol risk, 5% day loss, 2x exposure and absolute
    1.50 USDT risk ceilings. No quantity may increase above the archived plan.
    Full-portfolio daily loss and already reserved open risk are accounted for.
    Exchange limits must be supplied from a separately verified snapshot.
    """
    if (not isinstance(plan, dict) or
        plan.get("status") != "INDICATIVE_PLAN_ONLY_NOT_EXECUTABLE" or
        any(plan.get(k) is not False for k in
            ("orders_sent", "execution_authorized", "risk_snapshot_approved"))):
        raise ValueError("non_executable_plan_required")
    side = plan.get("side")
    if side not in ("long", "short"):
        raise ValueError("invalid_side")
    p = {key: _decimal(plan.get(key), key) for key in
         ("entry", "stop", "target", "quantity")}
    entry, stop, target, original = (
        p["entry"], p["stop"], p["target"], p["quantity"])
    if min(p.values()) <= 0:
        raise ValueError("invalid_plan_prices_or_quantity")
    if not (stop < entry < target if side == "long"
            else target < entry < stop):
        raise ValueError("invalid_brackets")

    numbers = {key: _decimal(value, key) for key, value in {
        "next_candle_open": next_candle_open, "amount_step": amount_step,
        "min_amount": min_amount, "min_notional": min_notional,
        "paper_equity": paper_equity, "day_start_equity": day_start_equity,
        "available_margin": available_margin,
        "portfolio_equity": portfolio_equity,
        "portfolio_day_start_equity": portfolio_day_start_equity,
        "portfolio_open_risk": portfolio_open_risk,
        "fee_rate": fee_rate, "slippage_rate": slippage_rate
    }.items()}
    a = numbers
    if any(a[k] <= 0 for k in (
            "next_candle_open", "amount_step", "paper_equity",
            "day_start_equity", "portfolio_equity",
            "portfolio_day_start_equity")):
        raise ValueError("invalid_positive_input")
    if any(a[k] < 0 for k in (
            "min_amount", "min_notional", "available_margin",
            "portfolio_open_risk", "fee_rate", "slippage_rate")):
        raise ValueError("invalid_nonnegative_input")
    if a["available_margin"] > a["paper_equity"]:
        raise ValueError("unverified_available_margin")
    if a["paper_equity"] > a["portfolio_equity"]:
        raise ValueError("invalid_portfolio_balance")
    if a["day_start_equity"] > a["portfolio_day_start_equity"]:
        raise ValueError("invalid_portfolio_day_start")

    result = {"status": "REJECTED_RESEARCH_ONLY", "orders_sent": False,
              "execution_authorized": False, "original_quantity": str(original)}
    if (a["paper_equity"] <= a["day_start_equity"] * Decimal("0.95") or
        a["portfolio_equity"] <=
            a["portfolio_day_start_equity"] * Decimal("0.95")):
        return {**result, "reason": "daily_loss_limit"}

    slip = a["slippage_rate"]
    fee = a["fee_rate"]
    open_price = a["next_candle_open"]
    fill = open_price * (1 + slip if side == "long" else 1 - slip)
    if fill <= 0:
        return {**result, "reason": "invalid_fill"}
    if not (stop < fill < target if side == "long"
            else target < fill < stop):
        return {**result, "reason": "gap_through_bracket"}

    # Match offline_plan_replay risk formula, including adverse entry/exit
    # slippage and entry/stop taker fees. Real slippage can be larger.
    per_unit_risk = abs(fill - stop) + fee * (fill + stop) + slip * stop
    if per_unit_risk <= 0:
        raise ValueError("invalid_risk_unit")

    risk_budget = min(
        Decimal("1.50"),
        a["paper_equity"] * Decimal("0.01"),
        a["paper_equity"] - a["day_start_equity"] * Decimal("0.95"),
        a["portfolio_equity"] -
          a["portfolio_day_start_equity"] * Decimal("0.95") -
          a["portfolio_open_risk"],
    )
    if risk_budget <= 0 or a["available_margin"] <= 0:
        return {**result, "reason": "no_risk_or_margin_budget"}

    cap = min(original, risk_budget / per_unit_risk,
              a["available_margin"] * 2 / fill)
    step = a["amount_step"]
    quantity = (cap / step).to_integral_value(rounding=ROUND_DOWN) * step
    notional = quantity * fill
    if (quantity <= 0 or quantity < a["min_amount"] or
            notional < a["min_notional"]):
        return {**result, "reason": "exchange_minimum_or_dust",
                "max_theoretical_quantity": str(quantity),
                "risk_budget_usdt": str(risk_budget)}
    estimated_risk = quantity * per_unit_risk
    if (estimated_risk > risk_budget or estimated_risk > Decimal("1.50")
            or notional > a["available_margin"] * 2
            or quantity > original):
        raise ValueError("research_sizing_invariant_failed")
    return {
        "status": "RESIZED_RESEARCH_ONLY",
        "orders_sent": False,
        "execution_authorized": False,
        "original_quantity": str(original),
        "research_quantity": str(quantity),
        "expected_fill_usdt": str(fill),
        "notional_usdt": str(notional),
        "risk_budget_usdt": str(risk_budget),
        "estimated_stop_risk_usdt": str(estimated_risk),
        "estimated_margin_usdt": str(notional / 2),
        "notes": "hypothetical next-candle fill; not a trade authorization",
    }
