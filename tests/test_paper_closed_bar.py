"""Offline tests that reject future, partial and pre-entry market data."""
from decimal import Decimal as D

import pytest

from research.paper_closed_bar import ClosedBar, apply_closed_bar
from research.paper_order_store import DurablePaperOrders


def test_reject_future_and_partial_candles(tmp_path):
    store = DurablePaperOrders(tmp_path / "paper.sqlite3")
    store.open("uid", "LONG", "1", "100", "98", "104", 100)
    bar = ClosedBar(100000, 105000, D(105), D(99), D(103), True)
    with pytest.raises(ValueError, match="future"):
        apply_closed_bar(store, "uid", bar, 104999)
    with pytest.raises(ValueError, match="unconfirmed"):
        apply_closed_bar(store, "uid", ClosedBar(100000, 105000, D(105), D(99), D(103), False), 105000)
    assert store.get("uid").status == "OPEN"


def test_closed_candle_lifecycle_and_restart(tmp_path):
    path = tmp_path / "paper.sqlite3"
    store = DurablePaperOrders(path)
    store.open("uid", "LONG", "1", "100", "98", "104", 100)
    with pytest.raises(ValueError, match="pre-entry"):
        apply_closed_bar(store, "uid", ClosedBar(99000, 104000, D(105), D(99), D(103), True), 104000)
    closed = apply_closed_bar(store, "uid", ClosedBar(100000, 105000, D(105), D(99), D(103), True), 105000)
    assert closed.status == "EXECUTED_TP"
    assert DurablePaperOrders(path).get("uid") == closed


def test_six_closed_5m_bars_expire_paper_at_exact_30_minutes(tmp_path):
    store = DurablePaperOrders(tmp_path / "thirty-minutes.sqlite3")
    store.open("expiry", "LONG", "1", "100", "98", "104", 0)
    for index in range(6):
        start = index * 300000
        bar = ClosedBar(
            start, start + 299999, D(101), D(99), D(100), True,
        )
        result = apply_closed_bar(store, "expiry", bar, bar.close_ms)
        assert result.status == ("EXPIRED" if index == 5 else "OPEN")
    assert result.expires_at == 1800
    assert result.net_pnl is not None
