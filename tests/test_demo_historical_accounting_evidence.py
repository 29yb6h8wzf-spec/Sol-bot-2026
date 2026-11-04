"""Offline accounting checks for historical Demo evidence.

These tests only validate supplied historical figures. They do not query Binance,
establish order ownership, or approve trading.
"""
from decimal import Decimal


def money(value):
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("invalid_money")
    return result


def compare_historical_totals(fill_rows, income):
    if not isinstance(fill_rows, list) or not isinstance(income, dict):
        raise ValueError("invalid_evidence")
    if any(not isinstance(row, dict) for row in fill_rows):
        raise ValueError("invalid_fill_row")
    realized = sum((money(r["realized"]) for r in fill_rows), Decimal("0"))
    fees = sum((money(r["fee"]) for r in fill_rows), Decimal("0"))
    if any(money(r["fee"]) < 0 for r in fill_rows):
        raise ValueError("negative_fee")
    account_realized = money(income["realized"])
    account_fees = money(income["commissions"])
    funding = money(income["funding"])
    account_net = money(income["net"])
    if account_realized + account_fees + funding != account_net:
        raise ValueError("inconsistent_account_income")
    return {
        "realized_gap": str(account_realized - realized),
        "commission_gap": str(account_fees + fees),
        "income_matched": realized == account_realized and -fees == account_fees,
        "order_ownership_verified": False,
        "whole_account_coverage_verified": False,
        "virtual_allocation_reconciled": False,
        "execution_authorized": False,
        "orders_sent": False,
    }


def test_november_3_demo_observations_match():
    rows = [
        {"realized": "0", "fee": "0.0025606"},
        {"realized": "-0.00050999", "fee": "0.00256039"},
        {"realized": "0", "fee": "0.00395194"},
        {"realized": "0", "fee": "0.00395194"},
    ]
    income = {"realized": "-0.00050999", "commissions": "-0.01302487",
              "funding": "0", "net": "-0.01353486"}
    result = compare_historical_totals(rows, income)
    assert result["income_matched"] is True
    assert result["realized_gap"] == "0E-8" or money(result["realized_gap"]) == 0
    assert money(result["commission_gap"]) == 0
    assert result["order_ownership_verified"] is False
    assert result["execution_authorized"] is False


def test_missing_fee_cannot_match():
    rows = [{"realized": "0", "fee": "0.01"}]
    income = {"realized": "0", "commissions": "-0.02",
              "funding": "0", "net": "-0.02"}
    assert compare_historical_totals(rows, income)["income_matched"] is False


def test_account_net_inconsistency_rejected():
    rows = []
    income = {"realized": "0", "commissions": "0",
              "funding": "0", "net": "1"}
    try:
        compare_historical_totals(rows, income)
    except ValueError:
        pass
    else:
        raise AssertionError("must reject inconsistent account income")


def test_nan_rejected():
    try:
        compare_historical_totals([{"realized": "NaN", "fee": "0"}],
                                  {"realized": "0", "commissions": "0",
                                   "funding": "0", "net": "0"})
    except ValueError:
        pass
    else:
        raise AssertionError("must reject NaN")
