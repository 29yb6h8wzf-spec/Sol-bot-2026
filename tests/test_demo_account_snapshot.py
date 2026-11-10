"""Offline tests for authenticated read-only Binance Demo snapshot."""
import time
from urllib.parse import urlsplit
import pytest

from demo_account_snapshot import (
    DemoSnapshotError, install_get_only_guard, read_snapshot, read_snapshots,
)


class FakeExchange:
    def __init__(self):
        self.urls = {"api": {
            "fapiPublic": "https://demo-fapi.binance.com/fapi/v1",
            "fapiPrivateV2": "https://demo-fapi.binance.com/fapi/v2",
            "fapiPrivateV3": "https://demo-fapi.binance.com/fapi/v3",
        }}
        self.calls = []

    def fetch(self, url, method="GET", headers=None, body=None):
        self.calls.append((url, method))
        return {"ok": True}

    def fapiPrivateV3GetAccount(self):
        return {"assets": [{"asset": "USDT", "walletBalance": "4500",
                            "availableBalance": "4500"}]}

    def fapiPrivateV2GetPositionRisk(self):
        return [{"symbol": "SOLUSDT", "positionAmt": "0",
                 "marginType": "isolated", "leverage": "2"},
                {"symbol": "XRPUSDT", "positionAmt": "0",
                 "marginType": "isolated", "leverage": "2"}]

    def fapiPrivateGetOpenOrders(self):
        return []

    def fapiPrivateGetOpenAlgoOrders(self):
        return {"orders": []}

    def fapiPrivateGetPositionSideDual(self):
        return {"dualSidePosition": False}

    def fapiPublicGetExchangeInfo(self):
        return {"symbols": [{"symbol": "SOLUSDT", "status": "TRADING",
                             "filters": [{"filterType": "MIN_NOTIONAL",
                                          "notional": "5"}]}]}

    def fapiPrivateGetIncome(self, params):
        assert params["limit"] == 1000
        return [{"incomeType": "REALIZED_PNL", "income": "-2.0"},
                {"incomeType": "COMMISSION", "income": "-0.1"},
                {"incomeType": "FUNDING_FEE", "income": "0.05"},
                {"incomeType": "TRANSFER", "income": "100"}]


def test_get_only_guard_blocks_real_and_mutations():
    ex = install_get_only_guard(FakeExchange())
    assert ex.fetch("https://demo-fapi.binance.com/fapi/v1/time") == {"ok": True}
    for url, method in [
        ("https://fapi.binance.com/fapi/v1/time", "GET"),
        ("http://demo-fapi.binance.com/fapi/v1/time", "GET"),
        ("https://demo-fapi.binance.com/api/v3/account", "GET"),
        ("https://demo-fapi.binance.com/fapi/v1/order", "POST"),
        ("https://demo-fapi.binance.com:443/fapi/v1/time", "GET"),
    ]:
        with pytest.raises(DemoSnapshotError):
            ex.fetch(url, method)


def test_guard_refuses_live_configured_client():
    ex = FakeExchange()
    ex.urls["api"]["fapiPublic"] = "https://fapi.binance.com/fapi/v1"
    with pytest.raises(DemoSnapshotError, match="non_demo_futures_url"):
        install_get_only_guard(ex)


def test_snapshot_account_wide_flat_and_daily_pnl():
    ex = install_get_only_guard(FakeExchange())
    snap = read_snapshot(ex, "SOLUSDT")
    assert snap["endpoint"] == "https://demo-fapi.binance.com"
    assert snap["positions_count"] == 0
    assert snap["orders_count"] == snap["algo_orders_count"] == 0
    assert snap["one_way"] is True
    assert snap["leverage"] == 2
    assert snap["wallet_usdt"] == "4500"
    assert snap["realized_pnl_today_usdt"] == "-2.05"


def test_no_unguarded_snapshot():
    with pytest.raises(DemoSnapshotError, match="guard_not_installed"):
        read_snapshot(FakeExchange(), "SOLUSDT")


def test_unknown_symbol_fails_closed():
    ex = install_get_only_guard(FakeExchange())
    with pytest.raises(DemoSnapshotError, match="unsupported_symbol"):
        read_snapshot(ex, "BTCUSDT")


def test_incomplete_income_history_fails_closed():
    ex = install_get_only_guard(FakeExchange())
    ex.fapiPrivateGetIncome = lambda _: [
        {"incomeType": "REALIZED_PNL", "income": "-1"} for _ in range(1000)]
    with pytest.raises(DemoSnapshotError, match="income_history_may_be_truncated"):
        read_snapshot(ex, "SOLUSDT")


def test_existing_position_is_visible():
    ex = install_get_only_guard(FakeExchange())
    ex.fapiPrivateV2GetPositionRisk = lambda: [
        {"symbol": "SOLUSDT", "positionAmt": "1",
         "marginType": "isolated", "leverage": "2"}]
    snap = read_snapshot(ex, "SOLUSDT")
    assert snap["positions_count"] == 1


def test_missing_flat_position_row_fails_closed():
    ex = install_get_only_guard(FakeExchange())
    ex.fapiPrivateV2GetPositionRisk = lambda: [
        {"symbol": "XRPUSDT", "positionAmt": "0",
         "marginType": "isolated", "leverage": "2"}]
    with pytest.raises(DemoSnapshotError, match="symbol_position_inventory_missing"):
        read_snapshot(ex, "SOLUSDT")


def test_atomic_pair_uses_one_authenticated_account_inventory():
    ex = install_get_only_guard(FakeExchange())
    counts = {"account": 0}
    original = ex.fapiPrivateV3GetAccount
    def counted():
        counts["account"] += 1
        return original()
    ex.fapiPrivateV3GetAccount = counted
    ex.fapiPublicGetExchangeInfo = lambda: {"symbols": [
        {"symbol": s, "status": "TRADING",
         "filters": [{"filterType": "MIN_NOTIONAL", "notional": "5"}]}
        for s in ("SOLUSDT", "XRPUSDT")]}
    snapshots = read_snapshots(ex)
    assert counts["account"] == 1
    assert snapshots["SOLUSDT"]["observed_at"] == snapshots["XRPUSDT"]["observed_at"]
    assert snapshots["SOLUSDT"]["wallet_usdt"] == snapshots["XRPUSDT"]["wallet_usdt"]
