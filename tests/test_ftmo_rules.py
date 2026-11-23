from datetime import date
from decimal import Decimal as D

import pytest

from ftmo_rules import (approve_entry, best_day_ok, breached, floors, min_days_ok,
                        profit_target_met, trading_day)

ISC = 100000


def entry(plan="two_step_challenge", **kw):
    args = dict(isc=ISC, equity=ISC, midnight_balance=ISC, open_risk=0, proposed_risk=400,
                proposed_notional=30000, used_margin=0, est_costs=40, requests_today=10)
    args.update(kw)
    return approve_entry(plan, **args)


def test_two_step_floors_static():
    assert floors("two_step_challenge", ISC, 104000) == (D("99000.00"), D("90000.00"))


def test_one_step_trailing_floor_moves_up_only():
    assert floors("one_step", ISC, 104000, highest_prior_midnight=104000) == (D("101000.00"), D("94000.00"))
    assert floors("one_step", ISC, 98000, highest_prior_midnight=97000)[1] == D("90000.00")


def test_daily_breach_is_equity_based():
    assert breached("two_step_challenge", ISC, 94999, 100000) == "max_daily_loss"
    assert breached("two_step_challenge", ISC, 95000, 100000) == "max_daily_loss"
    assert breached("two_step_challenge", ISC, 95001, 100000) is None


def test_max_loss_takes_priority():
    assert breached("one_step", ISC, 93500, 95000, highest_prior_midnight=104000) == "max_loss"


def test_invalid_counts_as_breach():
    assert breached("two_step_challenge", ISC, float("nan"), ISC) == "invalid_input"
    assert breached("nope", ISC, ISC, ISC) == "invalid_input"


def test_approve_small_trade():
    assert entry() == (True, "approved_offline_only")


def test_per_trade_cap_half_percent():
    assert entry(proposed_risk=501) == (False, "per_trade_risk")


def test_worst_case_daily_budget():
    # 2-step: floor 95,000 + 1% safety = 96,000; equity 96,400 - 400 risk - 40 costs < guard
    assert entry(equity=96400) == (False, "daily_loss_budget")


def test_open_risk_counts():
    assert entry(open_risk=3600) == (False, "daily_loss_budget")


def test_one_step_tighter_daily():
    assert entry("one_step", equity=98400) == (False, "daily_loss_budget")
    assert entry("two_step_challenge", equity=98400)[0] is True


def test_trailing_max_loss_budget():
    ok, reason = entry("one_step", equity=95300, midnight_balance=95300, highest_prior_midnight=104000)
    assert (ok, reason) == (False, "max_loss_budget")


def test_leverage_and_margin():
    assert entry(leverage=5) == (False, "leverage_cap")
    assert entry(proposed_notional=400000) == (False, "insufficient_margin")


def test_request_budget_well_below_ftmo_2000():
    assert entry(requests_today=1000) == (False, "request_budget")


@pytest.mark.parametrize("bad", [dict(equity="inf"), dict(proposed_risk=0), dict(open_risk=-1),
                                 dict(requests_today=True), dict(isc=True), dict(est_costs=None)])
def test_fail_closed(bad):
    assert entry(**bad)[0] is False


def test_profit_target_requires_flat():
    assert profit_target_met("two_step_challenge", ISC, 110000, 0) is True
    assert profit_target_met("two_step_challenge", ISC, 110000, 1) is False
    assert profit_target_met("two_step_verification", ISC, 105000, 0) is True


def test_best_day_rule_one_step_only():
    assert best_day_ok("one_step", [6000, 2000, 2000]) is False
    assert best_day_ok("one_step", [4000, 3000, 3000]) is True
    assert best_day_ok("one_step", [5000, -1000, 1000]) is False
    assert best_day_ok("two_step_challenge", [9000]) is True


def test_min_days():
    assert min_days_ok("two_step_challenge", 3) is False
    assert min_days_ok("two_step_challenge", 4) is True
    assert min_days_ok("one_step", 0) is True


def test_trading_day_uses_prague_midnight():
    # 2026-11-23 23:30 UTC == 2026-11-24 00:30 CET
    assert trading_day(1795476600000) == date(2026, 11, 24)
    # summer: 2026-07-01 21:59 UTC == 23:59 CEST, still Jul 1
    assert trading_day(1782943140000) == date(2026, 7, 1)
