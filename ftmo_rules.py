"""Offline, fail-closed FTMO Trading Objectives guard (forex first); never places orders.

Rules modelled (source: ftmo.com/en/trading-objectives, checked 2026-11-23):

* 2-Step (Challenge + Verification)
  - Max Daily Loss floor = balance at 00:00 CE(S)T - 5% of initial capital (ISC)
  - Max Loss floor       = 90% of ISC, static
  - Profit target        = 10% (Challenge) / 5% (Verification), all positions closed
  - Minimum 4 trading days (a day on which at least one position is opened)
* 1-Step
  - Max Daily Loss floor = balance at 00:00 CE(S)T - 3% of ISC
  - Max Loss floor       = max(ISC, highest earlier 00:00 balance) - 10% of ISC,
                           trailing end-of-day, only moves up
  - Profit target        = 10%, all positions closed
  - Best Day rule        = best day profit <= 50% of total closed profit

Both floors are measured against *equity* (balance + floating P/L, swaps,
commissions), so the entry check below assumes every open stop and the new
stop are hit, plus costs, plus an extra safety margin for gaps/slippage.

Forbidden-practice guard: FTMO flags EAs exceeding 2,000 server requests per
day; we stop far earlier.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

D = Decimal
PRAGUE = ZoneInfo("Europe/Prague")
FTMO_REQUEST_LIMIT = 2000
INTERNAL_REQUEST_LIMIT = 1000
# FTMO normal-account leverage by asset class (Swing accounts are lower: forex 1:30).
LEVERAGE_CAPS = {"forex": D("100"), "crypto": D("3")}
CRYPTO_LEVERAGE_CAP = LEVERAGE_CAPS["crypto"]


@dataclass(frozen=True)
class Plan:
    name: str
    daily_loss: Decimal
    max_loss: Decimal
    profit_target: Decimal
    trailing_max_loss: bool
    min_trading_days: int
    best_day_share: Decimal | None


PLANS = {
    "two_step_challenge": Plan("two_step_challenge", D("0.05"), D("0.10"), D("0.10"), False, 4, None),
    "two_step_verification": Plan("two_step_verification", D("0.05"), D("0.10"), D("0.05"), False, 4, None),
    "one_step": Plan("one_step", D("0.03"), D("0.10"), D("0.10"), True, 0, D("0.50")),
}


def _dec(*values):
    out = []
    for value in values:
        if isinstance(value, bool):
            raise ValueError("invalid_input")
        try:
            number = D(str(value))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("invalid_input") from None
        if not number.is_finite():
            raise ValueError("invalid_input")
        out.append(number)
    return out


def _plan(name):
    plan = PLANS.get(name)
    if plan is None:
        raise ValueError("unknown_plan")
    return plan


def trading_day(ts_ms):
    """FTMO trading day (00:00-23:59:59 CE(S)T) for a UTC epoch-ms timestamp."""
    if type(ts_ms) is not int or ts_ms < 0:
        raise ValueError("invalid_timestamp")
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).astimezone(PRAGUE).date()


def floors(plan_name, isc, midnight_balance, highest_prior_midnight=None):
    """Return (daily_floor, max_loss_floor) as equity levels that must never be touched."""
    plan = _plan(plan_name)
    isc, midnight_balance = _dec(isc, midnight_balance)
    if isc <= 0 or midnight_balance <= 0:
        raise ValueError("invalid_account")
    daily_floor = midnight_balance - plan.daily_loss * isc
    if plan.trailing_max_loss:
        peak = isc
        if highest_prior_midnight is not None:
            (prior,) = _dec(highest_prior_midnight)
            if prior <= 0:
                raise ValueError("invalid_account")
            peak = max(peak, prior)
        max_floor = peak - plan.max_loss * isc
    else:
        max_floor = isc - plan.max_loss * isc
    return daily_floor, max_floor


def breached(plan_name, isc, equity, midnight_balance, highest_prior_midnight=None):
    """Return the violated rule name, or None. Invalid input counts as a breach."""
    try:
        daily_floor, max_floor = floors(plan_name, isc, midnight_balance, highest_prior_midnight)
        (equity,) = _dec(equity)
    except ValueError:
        return "invalid_input"
    if equity <= max_floor:
        return "max_loss"
    if equity <= daily_floor:
        return "max_daily_loss"
    return None


def approve_entry(plan_name, *, isc, equity, midnight_balance, open_risk, proposed_risk,
                  proposed_notional, used_margin, est_costs, requests_today,
                  highest_prior_midnight=None, asset_class="forex", leverage=D("30"),
                  per_trade_fraction=D("0.005"), safety_fraction=D("0.01")):
    """Approve a new entry only if worst-case equity stays clear of both FTMO floors.

    open_risk / proposed_risk: loss to stop (incl. expected slippage) in account currency.
    est_costs: commission + spread + swap estimate for the new trade.
    safety_fraction: extra ISC fraction kept between worst case and the nearest floor.
    """
    try:
        plan = _plan(plan_name)
        daily_floor, max_floor = floors(plan_name, isc, midnight_balance, highest_prior_midnight)
        (isc, equity, open_risk, proposed_risk, proposed_notional, used_margin, est_costs,
         leverage, per_trade_fraction, safety_fraction) = _dec(
            isc, equity, open_risk, proposed_risk, proposed_notional, used_margin, est_costs,
            leverage, per_trade_fraction, safety_fraction)
    except ValueError as exc:
        return False, str(exc)
    if type(requests_today) is not int or requests_today < 0:
        return False, "invalid_input"
    if min(open_risk, used_margin, est_costs) < 0 or proposed_risk <= 0 or proposed_notional <= 0:
        return False, "invalid_input"
    if equity <= 0:
        return False, "invalid_account"
    if not (D("0") < per_trade_fraction <= D("0.01")) or not (D("0") <= safety_fraction < plan.daily_loss):
        return False, "invalid_config"
    cap = LEVERAGE_CAPS.get(asset_class)
    if cap is None:
        return False, "invalid_asset_class"
    if not (D("1") <= leverage <= cap):
        return False, "leverage_cap"
    if requests_today >= INTERNAL_REQUEST_LIMIT:
        return False, "request_budget"
    if breached(plan_name, isc, equity, midnight_balance, highest_prior_midnight):
        return False, "already_breached"
    if proposed_risk > per_trade_fraction * isc:
        return False, "per_trade_risk"
    guard = max(daily_floor, max_floor) + safety_fraction * isc
    worst_equity = equity - open_risk - proposed_risk - est_costs
    if worst_equity <= guard:
        return False, "max_loss_budget" if max_floor >= daily_floor else "daily_loss_budget"
    if used_margin + proposed_notional / leverage > equity:
        return False, "insufficient_margin"
    return True, "approved_offline_only"


def profit_target_met(plan_name, isc, balance, open_positions):
    plan = _plan(plan_name)
    isc, balance = _dec(isc, balance)
    if type(open_positions) is not int or open_positions < 0 or isc <= 0:
        raise ValueError("invalid_input")
    return open_positions == 0 and balance >= isc * (D("1") + plan.profit_target)


def best_day_ok(plan_name, daily_closed_pnl):
    """1-Step consistency: best day <= 50% of total closed P&L. Not a breach, a pass gate."""
    plan = _plan(plan_name)
    if plan.best_day_share is None:
        return True
    pnls = _dec(*daily_closed_pnl) if daily_closed_pnl else []
    total = sum(pnls, D("0"))
    if total <= 0:
        return False
    return max(pnls) <= plan.best_day_share * total


def min_days_ok(plan_name, trading_days):
    plan = _plan(plan_name)
    if type(trading_days) is not int or trading_days < 0:
        raise ValueError("invalid_input")
    return trading_days >= plan.min_trading_days
