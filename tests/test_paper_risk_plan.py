"""Offline sizing stays inside fixed paper risk and leverage limits."""
from decimal import Decimal

import pytest

from research.paper_risk_plan import paper_plan


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
def test_plan_respects_risk_and_leverage(side):
    p = paper_plan("100", side)
    assert Decimal(p["estimated_risk_usd"]) <= Decimal("1.50")
    assert Decimal(p["estimated_notional"]) <= Decimal("300")
    if side == "LONG":
        assert Decimal(p["stop"]) < 100 < Decimal(p["target"])
    else:
        assert Decimal(p["target"]) < 100 < Decimal(p["stop"])


@pytest.mark.parametrize("kwargs", [
    {"leverage": "3"}, {"risk_usd": "2"}, {"stop_fraction": "0.03"},
    {"capital": "0"}, {"quantity_step": "0"},
])
def test_plan_rejects_unsafe_inputs(kwargs):
    with pytest.raises(ValueError):
        paper_plan("100", "LONG", **kwargs)


def test_plan_rejects_unfillable_quantity():
    with pytest.raises(ValueError, match="below step"):
        paper_plan("100", "LONG", quantity_step="1000")
