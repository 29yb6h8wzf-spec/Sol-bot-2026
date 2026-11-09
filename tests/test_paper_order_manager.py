"""Offline acceptance tests for the paper-only order manager."""
from decimal import Decimal as D

import pytest

from research.paper_order_manager import PaperOrderManager


def test_long_tp_fees_slippage_and_idempotency():
    manager = PaperOrderManager()
    trade = manager.open("signal-1", "LONG", "1", "100", "98", "104", 100)
    assert manager.open("signal-1", "LONG", "999", "100", "98", "104", 100) is trade
    assert trade.entry == D("100.0200")
    result = manager.update("signal-1", "104", "99", "103", 101)
    assert result.status == "EXECUTED_TP"
    assert result.net_pnl < result.gross_pnl
    assert manager.update("signal-1", "105", "97", "100", 102) == result


def test_same_bar_stop_first_and_short():
    manager = PaperOrderManager("0.0006")
    manager.open("short", "SHORT", "2", "100", "102", "96", 1)
    result = manager.update("short", "103", "95", "100", 2)
    assert result.status == "EXECUTED_SL"
    assert result.net_pnl < 0


def test_expiry_and_invalid_order():
    manager = PaperOrderManager()
    manager.open("exp", "LONG", "1", "100", "99", "105", 10, holding_seconds=5)
    assert manager.update("exp", "101", "100", "100.5", 15).status == "EXPIRED"
    with pytest.raises(ValueError):
        manager.open("bad", "LONG", "1", "100", "105", "99", 10)
