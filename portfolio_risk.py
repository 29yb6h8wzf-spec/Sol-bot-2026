"""Offline, fail-closed portfolio risk arithmetic; never places orders."""
from decimal import Decimal, InvalidOperation


def approve(equity, day_start, used_margin, proposed_notional, proposed_risk,
            leverage=2, open_risk=0):
    try:
        values = [Decimal(str(v)) for v in (
            equity, day_start, used_margin, proposed_notional,
            proposed_risk, leverage, open_risk)]
    except (InvalidOperation, TypeError, ValueError):
        return False, "invalid_input"
    if not all(v.is_finite() for v in values):
        return False, "invalid_input"
    equity, day_start, used_margin, proposed_notional, proposed_risk, leverage, open_risk = values
    if equity <= 0 or day_start <= 0 or equity > 150 or day_start > 150:
        return False, "invalid_account"
    if leverage < 1 or leverage > 2:
        return False, "invalid_account"
    if min(used_margin, proposed_notional, proposed_risk, open_risk) < 0:
        return False, "invalid_input"
    daily_budget = min(Decimal("7.50"), day_start * Decimal("0.05"))
    if day_start - equity >= daily_budget:
        return False, "daily_loss_limit"
    if proposed_risk > Decimal("1.50"):
        return False, "per_trade_risk"
    if proposed_risk + open_risk > min(
        daily_budget - (day_start - equity), equity):
        return False, "portfolio_risk_budget"
    if used_margin + proposed_notional / leverage > equity:
        return False, "insufficient_margin"
    return True, "approved_offline_only"
