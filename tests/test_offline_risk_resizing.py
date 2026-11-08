"""Offline sizing: no exchange clients, no secrets, and no order requests."""
from decimal import Decimal as D
import pytest

from futures_engine.offline_risk_resizing import research_resize


def plan(**changes):
    obj = {"status": "INDICATIVE_PLAN_ONLY_NOT_EXECUTABLE",
           "orders_sent": False, "execution_authorized": False,
           "risk_snapshot_approved": False, "side": "short",
           "entry": "100", "stop": "101", "target": "98",
           "quantity": "2", "closed_5m_candle_ms": 1793889300000}
    obj.update(changes)
    return obj


def sized(p=None, **changes):
    args = {"next_candle_open": "100.2", "amount_step": "0.01",
            "min_amount": "0.01", "min_notional": "5"}
    args.update(changes)
    return research_resize(p or plan(), **args)


def test_four_way_paper_equity_limit_is_stricter_than_global_cap():
    original = plan()
    before = dict(original)
    r = sized(original)
    assert r["status"] == "RESIZED_RESEARCH_ONLY"
    assert r["orders_sent"] is False
    assert r["execution_authorized"] is False
    assert D(r["research_quantity"]) < D(original["quantity"])
    assert D(r["estimated_stop_risk_usdt"]) <= D("0.375")
    assert D(r["notional_usdt"]) <= D("75")
    assert D(r["estimated_margin_usdt"]) <= D("37.50")
    assert original == before


def test_full_150_usdt_margin_is_not_assumed_from_four_37_5_ledgers():
    # At ~79k BTC, 37.50 margin x2 allows <0.001 BTC. A historical
    # symbol min qty of 0.001 is used as an explicit offline fixture.
    btc = plan(entry="79000", stop="79200", target="78600",
               quantity="0.003")
    rejection = research_resize(
        btc, next_candle_open="79000", amount_step="0.001",
        min_amount="0.001", min_notional="5")
    assert rejection["status"] == "REJECTED_RESEARCH_ONLY"
    assert rejection["reason"] == "exchange_minimum_or_dust"

    # Illustrative single-allocation scenario. It is NOT today's active
    # per-coin Paper setup and is not permission to increase capital.
    hypothetical = research_resize(
        btc, next_candle_open="79000", amount_step="0.001",
        min_amount="0.001", min_notional="5",
        paper_equity="150", day_start_equity="150",
        available_margin="150")
    assert hypothetical["status"] == "RESIZED_RESEARCH_ONLY"
    assert D(hypothetical["estimated_stop_risk_usdt"]) <= D("1.50")


def test_existing_original_qty_is_never_increased():
    r = sized(plan(quantity="0.10"), amount_step="0.01")
    assert r["status"] == "RESIZED_RESEARCH_ONLY"
    assert D(r["research_quantity"]) <= D("0.10")


def test_conservative_fees_and_slippage_reduce_the_allowed_amount():
    low = sized(fee_rate="0", slippage_rate="0")
    high = sized(fee_rate="0.0012", slippage_rate="0.0010")
    assert low["status"] == high["status"] == "RESIZED_RESEARCH_ONLY"
    assert D(high["research_quantity"]) < D(low["research_quantity"])


def test_daily_symbol_loss_breaker_fails_closed():
    r = sized(paper_equity="35.60", day_start_equity="37.50",
              available_margin="35.60")
    assert r["status"] == "REJECTED_RESEARCH_ONLY"
    assert r["reason"] == "daily_loss_limit"


def test_daily_portfolio_loss_breaker_fails_closed():
    r = sized(portfolio_equity="142.00",
              portfolio_day_start_equity="150")
    assert r["status"] == "REJECTED_RESEARCH_ONLY"
    assert r["reason"] == "daily_loss_limit"


def test_other_positions_reserved_risk_reduces_budget():
    r = sized(portfolio_open_risk="7.40")
    assert r["status"] == "RESIZED_RESEARCH_ONLY"
    assert D(r["estimated_stop_risk_usdt"]) <= D("0.10")


def test_no_available_total_risk_budget_fails_closed():
    r = sized(portfolio_open_risk="7.50")
    assert r["status"] == "REJECTED_RESEARCH_ONLY"
    assert r["reason"] == "no_risk_or_margin_budget"


def test_no_free_margin_fails_closed():
    r = sized(available_margin="0")
    assert r["status"] == "REJECTED_RESEARCH_ONLY"
    assert r["reason"] == "no_risk_or_margin_budget"


def test_exchange_min_notional_rejects_dust_after_rounding_down():
    r = sized(min_notional="100")
    assert r["status"] == "REJECTED_RESEARCH_ONLY"
    assert r["reason"] == "exchange_minimum_or_dust"


def test_gap_through_stop_never_opens_a_research_position():
    r = sized(next_candle_open="102")
    assert r["status"] == "REJECTED_RESEARCH_ONLY"
    assert r["reason"] == "gap_through_bracket"


def test_gap_beyond_target_is_also_rejected():
    r = sized(next_candle_open="97")
    assert r["status"] == "REJECTED_RESEARCH_ONLY"
    assert r["reason"] == "gap_through_bracket"


@pytest.mark.parametrize("flag", ["orders_sent",
                                 "execution_authorized",
                                 "risk_snapshot_approved"])
def test_executable_or_authorized_plan_is_never_accepted(flag):
    with pytest.raises(ValueError, match="non_executable_plan_required"):
        sized(plan(**{flag: True}))


def test_invalid_strategy_side_is_rejected():
    with pytest.raises(ValueError, match="invalid_side"):
        sized(plan(side="buy"))


@pytest.mark.parametrize("field,value", [
    ("next_candle_open", "NaN"),
    ("amount_step", "0"),
    ("min_amount", "-1"),
    ("min_notional", "-3"),
    ("fee_rate", "Infinity"),
    ("slippage_rate", "-0.1"),
    ("available_margin", "-2"),
    ("paper_equity", "0"),
])
def test_invalid_numeric_inputs_fail_closed(field, value):
    with pytest.raises(ValueError):
        sized(**{field: value})


def test_unverified_margin_exceeding_ledger_equity_fails_closed():
    with pytest.raises(ValueError, match="unverified_available_margin"):
        sized(available_margin="150")


def test_synthetic_order_fields_are_not_created_in_result():
    r = sized()
    assert "order" not in r and "api_key" not in r
    assert r["status"] == "RESIZED_RESEARCH_ONLY"
    assert r["orders_sent"] is False


def test_full_per_coin_risk_can_be_smaller_than_absolute_1_5_limit():
    r = sized()
    assert D(r["risk_budget_usdt"]) == D("0.375")
    assert D(r["estimated_stop_risk_usdt"]) <= D(r["risk_budget_usdt"])
