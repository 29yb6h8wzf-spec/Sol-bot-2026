"""Crash/restart and duplicate-signal acceptance tests for SQLite paper store."""
from decimal import Decimal as D
import pytest

from research.paper_order_store import DurablePaperOrders


def test_restart_preserves_open_and_closed_state(tmp_path):
    path = tmp_path / "paper.sqlite3"
    first = DurablePaperOrders(path)
    opened = first.open("uid-1", "LONG", "1", "100", "98", "104", 100)
    second = DurablePaperOrders(path)
    assert second.get("uid-1") == opened
    assert second.open("uid-1", "LONG", "999", "100", "98", "104", 100) == opened
    closed = second.update("uid-1", "104", "99", "103", 101)
    assert closed.status == "EXECUTED_TP"
    third = DurablePaperOrders(path)
    assert third.get("uid-1") == closed
    assert third.update("uid-1", "110", "90", "100", 102) == closed
    assert closed.net_pnl < closed.gross_pnl


def test_invalid_update_rolls_back_without_corrupting_state(tmp_path):
    store = DurablePaperOrders(tmp_path / "paper.sqlite3")
    opened = store.open("uid-2", "SHORT", D("2"), "100", "102", "96", 100)
    with pytest.raises(ValueError):
        store.update("uid-2", "90", "110", "100", 101)
    assert DurablePaperOrders(tmp_path / "paper.sqlite3").get("uid-2") == opened


def test_same_bar_stop_is_durable(tmp_path):
    path = tmp_path / "paper.sqlite3"
    store = DurablePaperOrders(path)
    store.open("uid-3", "LONG", "1", "100", "98", "104", 100)
    assert store.update("uid-3", "105", "97", "100", 101).status == "EXECUTED_SL"
    assert DurablePaperOrders(path).get("uid-3").status == "EXECUTED_SL"
