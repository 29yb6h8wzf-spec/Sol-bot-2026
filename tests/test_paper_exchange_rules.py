"""Pinned public Binance exchangeInfo filters are enforced in Paper sizing."""
from decimal import Decimal

import pytest

from research.paper_exchange_rules import (
    check_paper_exchange_plan,
    research_exchange_rules,
)
from research.paper_order_manager import PaperOrderManager
from research.paper_risk_plan import paper_plan


@pytest.mark.parametrize("symbol,step,tick", [
    ("XRP/USDT:USDT", "0.1", "0.0001"),
    ("SOL/USDT:USDT", "0.01", "0.0100"),
])
@pytest.mark.parametrize("side", ["LONG", "SHORT"])
def test_pinned_binance_filters_and_exact_stop_loss(symbol, step, tick, side):
    price = "1.0932" if symbol.startswith("XRP") else "100"
    plan = paper_plan(price, side, symbol=symbol)
    assert check_paper_exchange_plan(symbol, plan)
    assert Decimal(plan["quantity"]) % Decimal(step) == 0
    assert Decimal(plan["stop"]) % Decimal(tick) == 0
    assert Decimal(plan["target"]) % Decimal(tick) == 0
    assert Decimal(plan["estimated_risk_usd"]) <= Decimal("0.375")
    assert Decimal(plan["estimated_notional"]) <= Decimal(75)
    assert Decimal(plan["quantity"]) * Decimal(price) >= Decimal(5)
    manager = PaperOrderManager()
    manager.open(
        "exchange-rule-risk", side, plan["quantity"], plan["entry_mid"],
        plan["stop"], plan["target"], 0,
    )
    stop = Decimal(plan["stop"])
    entry = Decimal(plan["entry_mid"])
    high, low = (entry, stop) if side == "LONG" else (stop, entry)
    finished = manager.update("exchange-rule-risk", high, low, stop, 300)
    assert finished.status == "EXECUTED_SL"
    assert -Decimal("0.375") <= finished.net_pnl <= 0
    assert -finished.net_pnl == Decimal(plan["estimated_risk_usd"])


@pytest.mark.parametrize("symbol", ["XRP/USDT:USDT", "SOL/USDT:USDT"])
def test_exchange_rule_rejects_mismatched_step_and_below_min_notional(symbol):
    with pytest.raises(ValueError, match="quantity step conflicts"):
        paper_plan("100", "LONG", symbol=symbol, quantity_step="0.001")
    with pytest.raises(ValueError, match="min notional|below Binance"):
        paper_plan("1", "LONG", symbol=symbol, capital="1", risk_usd="0.01")


def test_exchange_rules_fail_closed_for_unrecognized_symbol():
    with pytest.raises(ValueError, match="missing pinned"):
        research_exchange_rules("BTC/USDT:USDT")


@pytest.mark.parametrize("symbol", ["XRP/USDT:USDT", "SOL/USDT:USDT"])
def test_per_market_allocation_and_one_percent_risk_are_hard_caps(symbol):
    with pytest.raises(ValueError, match="per-market"):
        paper_plan("100", "LONG", symbol=symbol, capital="150")
    with pytest.raises(ValueError, match="per-market"):
        paper_plan("100", "LONG", symbol=symbol, risk_usd="1.50")
