"""Offline-only sizing: never round a small position up to exchange minimum."""
from decimal import Decimal as D
import pytest
from tools.offline_symbol_viability import size_for_stop


@pytest.mark.parametrize("symbol,price,step,minqty,minnotional,stop,expected", [
    ("BTC", "75920.20", ".001", ".001", "50", ".003", False),
    ("BTC", "75920.20", ".001", ".001", "50", ".02", False),
    ("ETH", "2237.99", ".001", ".001", "20", ".005", True),
    ("ETH", "2237.99", ".001", ".001", "20", ".02", False),
    ("SOL", "89.53", ".01", ".01", "5", ".02", True),
    ("XRP", "1.1628", ".1", ".1", "5", ".02", True),
])
def test_viability(symbol, price, step, minqty, minnotional, stop, expected):
    result = size_for_stop(price, step, minqty, minnotional, stop)
    assert result["tradable"] is expected
    qty, notional = D(result["quantity"]), D(result["notional"])
    assert qty % D(step) == 0
    assert notional <= D("75")
    assert D(result["stop_risk_before_fees"]) <= D(".375")
    assert result["rejection"] == (None if expected else "below_exchange_minimum")


def test_rejects_higher_leverage_or_risk():
    with pytest.raises(ValueError, match="risk_limit_exceeded"):
        size_for_stop("100", ".01", ".01", "5", ".01", leverage=3)
    with pytest.raises(ValueError, match="risk_limit_exceeded"):
        size_for_stop("100", ".01", ".01", "5", ".01", risk_fraction=".02")


def test_never_rounds_up_to_exchange_minimum():
    result = size_for_stop("75920.20", ".001", ".001", "50", ".003")
    assert D(result["quantity"]) == 0
    assert result["rejection"] == "below_exchange_minimum"

@pytest.mark.parametrize("price,step,minqty,minnotional,stop", [
    ("2237.99", ".001", ".001", "20", ".005"),
    ("89.53", ".01", ".01", "5", ".02"),
    ("1.1628", ".1", ".1", "5", ".02"),
])
def test_viability_matches_canonical_plan_trade(price, step, minqty, minnotional, stop):
    from futures_engine.core import Config, plan_trade
    result = size_for_stop(price, step, minqty, minnotional, stop)
    plan = plan_trade(Config(stop_fraction=D(stop)), "long", price,
                      D("37.50"), D("37.50"), minimum_amount=D(minqty),
                      amount_step=D(step), min_cost=D(minnotional))
    assert D(result["quantity"]) == D(plan["quantity"])
    assert D(result["max_estimated_loss_including_costs"]) == D(plan["max_estimated_loss"])

def test_cost_ratio_exceeds_15_percent_for_short_stops():
    for stop in (".003", ".005", ".01"):
        result = size_for_stop("89.53", ".01", ".01", "5", stop)
        assert D(result["round_trip_cost_fraction"]) / D(stop) > D(".15")
