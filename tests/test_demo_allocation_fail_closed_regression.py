"""Offline guard tests: a numerically balanced account is not an approved allocation."""
from datetime import datetime, timezone

import pytest

from demo_virtual_allocation import compute

NOW = int(datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc).timestamp())
MIDNIGHT = int(datetime(2026, 11, 4, tzinfo=timezone.utc).timestamp() * 1000)


def observation(source, **fields):
    return {"source": source, "observed_at": NOW, "orders_sent": False, **fields}


def evidence(*, unknown=0, realized="0", fees="0", net="0"):
    attr = observation(
        "binance_demo_four_symbol_trade_attribution_read_only",
        day_start_utc_ms=MIDNIGHT, status="AUDIT_ONLY_NOT_EXECUTABLE",
        allocation_ledger_reconciled=False, execution_authorized=False,
        signalpilot_realized_pnl_usdt=realized,
        signalpilot_commissions_usdt=fees,
        signalpilot_net_before_funding_usdt=net,
        signalpilot_fills=0, unattributed_fills=unknown,
        registry_present=False,
    )
    account = observation(
        "binance_demo_observation_only",
        exposed_symbols=[], open_orders={}, open_algo_orders={},
        usdt_total="10000", usdt_free="10000",
    )
    exposure = observation(
        "binance_demo_account_wide_unrealized_read_only",
        exposed_symbols=[], open_position_count=0,
    )
    return attr, account, exposure


def test_clean_looking_account_is_still_blocked():
    result = compute(*evidence(), now=NOW)
    assert result["status"] == "BLOCKED_OBSERVATION_ONLY"
    assert result["allocation_ledger_reconciled"] is False
    assert result["execution_authorized"] is False
    assert result["orders_sent"] is False
    assert "VIRTUAL_ALLOCATION_NOT_EXCHANGE_SEGREGATED" in result["block_reasons"]
    assert "FOUR_SYMBOL_SCOPE_NOT_WHOLE_ACCOUNT" in result["block_reasons"]
    assert "FUNDING_NOT_ATTRIBUTED" in result["block_reasons"]


def test_unattributed_fills_cannot_be_treated_as_strategy_funds():
    result = compute(*evidence(unknown=5), now=NOW)
    assert result["unattributed_fills_today"] == 5
    assert result["indicative_virtual_balance_before_funding_usdt"] == "150"
    assert "UNATTRIBUTED_FILLS" in result["block_reasons"]
    assert result["execution_authorized"] is False


def test_below_capital_blocks_even_without_positions():
    attr, account, exposure = evidence()
    account["usdt_total"] = "149.99"
    result = compute(attr, account, exposure, now=NOW)
    assert "DEMO_ACCOUNT_BALANCE_BELOW_ALLOCATION" in result["block_reasons"]
    assert result["execution_authorized"] is False


@pytest.mark.parametrize("realized,fees,net", [
    ("1", "0.1", "1"),
    ("NaN", "0", "0"),
    ("0", "-1", "1"),
])
def test_invalid_attribution_fails_closed(realized, fees, net):
    with pytest.raises(ValueError):
        compute(*evidence(realized=realized, fees=fees, net=net), now=NOW)
