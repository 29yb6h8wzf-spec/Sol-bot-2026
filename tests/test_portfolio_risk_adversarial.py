"""Adversarial, offline checks for portfolio risk arithmetic."""
import pytest
from portfolio_risk import approve

BASE = dict(equity="150", day_start="150", used_margin="0",
            proposed_notional="100", proposed_risk="1.5",
            leverage=2, open_risk="0")


@pytest.mark.parametrize("field", list(BASE))
@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity", "not-a-number", None])
def test_nonfinite_or_unparseable_fail_closed(field, bad):
    assert approve(**{**BASE, field: bad})[0] is False


def test_exact_per_trade_limit_accepted_offline():
    assert approve(**BASE) == (True, "approved_offline_only")


def test_over_trade_limit_blocked():
    assert approve(**{**BASE, "proposed_risk": "1.500001"})[0] is False


def test_daily_loss_limit_blocks():
    assert approve(**{**BASE, "equity": "142.50"}) == (False, "daily_loss_limit")


def test_existing_open_risk_blocks_budget():
    assert approve(**{**BASE, "open_risk": "6.01"})[0] is False


def test_excessive_leverage_and_capital_blocked():
    assert approve(**{**BASE, "leverage": 3})[0] is False
    assert approve(**{**BASE, "equity": 151})[0] is False
