"""Adversarial non-finite paper risk checks (offline only)."""
from dataclasses import replace
from decimal import Decimal as D
import pytest
from futures_engine.core import Config, plan_trade


@pytest.mark.parametrize("field", [
    "risk_fraction", "daily_loss_fraction", "stop_fraction",
    "reward_multiple", "taker_fee", "slippage_fraction"
])
@pytest.mark.parametrize("bad", [D("NaN"), D("Infinity"), D("-Infinity")])
def test_config_rejects_nonfinite(field, bad):
    with pytest.raises(ValueError):
        replace(Config(), **{field: bad}).validate()


@pytest.mark.parametrize("field", ["entry", "equity", "day_start_equity", "amount_step", "minimum_amount", "min_cost"])
@pytest.mark.parametrize("bad", [D("NaN"), D("Infinity"), D("-Infinity")])
def test_trade_rejects_nonfinite_inputs(field, bad):
    args = dict(entry=D("100"), equity=D("150"), day_start_equity=D("150"),
                amount_step=D("0.001"), minimum_amount=D("0"), min_cost=D("0"))
    args[field] = bad
    with pytest.raises(ValueError):
        plan_trade(Config(), "long", **args)
