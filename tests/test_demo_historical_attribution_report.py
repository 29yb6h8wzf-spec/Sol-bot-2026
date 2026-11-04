"""Offline safety and provenance tests for historical attribution evidence."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from demo_historical_attribution_report import report

SYMBOL = "XRP/USDT:USDT"
DAY = "2026-11-03"
TS = 1793664000000


class Demo:
    urls = {"api": {"fapiPrivate": "https://demo-fapi.binance.com/fapi/v1"}}

    def __init__(self, trades, client="SPDEMO-abc"):
        self.trades = trades
        self.client = client
        self.reads = []

    def fetch_my_trades(self, symbol, since=None, limit=None):
        self.reads.append(("trades", symbol))
        return self.trades if symbol == SYMBOL else []

    def fetch_order(self, order_id, symbol):
        self.reads.append(("order", symbol))
        return {"id": order_id, "symbol": symbol, "clientOrderId": self.client}


def fill(trade_id="1", order_id="11", fee="0.1", pnl="1.5"):
    return {"id": trade_id, "order": order_id, "symbol": SYMBOL,
            "timestamp": TS, "fee": {"currency": "USDT", "cost": fee},
            "info": {"realizedPnl": pnl}}


def test_unattributed_without_registry(tmp_path):
    exchange = Demo([fill()])
    result = report(exchange, DAY, registry_path=tmp_path / "missing.json")
    assert result["total_fills"] == 1
    assert result["unattributed_fills"] == 1
    assert result["orders"][0]["ownership"] == "UNATTRIBUTED"
    assert result["orders"][0]["realized_pnl_usdt"] == "1.5"
    assert result["orders"][0]["commission_usdt"] == "0.1"
    assert result["execution_authorized"] is False
    assert result["orders_sent"] is False
    assert result["complete_account_coverage"] is False


def test_owned_requires_registry_and_exchange_match(tmp_path):
    import json
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({
        "schema_version": 1, "source": "signalpilot_demo_executor_registry",
        "execution_mode": "binance_demo", "orders": [{
            "symbol": SYMBOL, "order_id": "11", "client_order_id": "SPDEMO-abc"
        }]
    }))
    path.chmod(0o600)
    # Registry requires root-owned file; non-root runners must fail closed.
    if path.stat().st_uid != 0:
        with pytest.raises(ValueError):
            report(Demo([fill()]), DAY, registry_path=path)
        return
    try:
        result = report(Demo([fill()]), DAY, registry_path=path)
    except ValueError:
        # A malformed registry must never silently grant ownership.
        return
    assert result["orders"][0]["ownership"] == "SIGNALPILOT_CONFIRMED"
    assert report(Demo([fill()], client="OTHER"), DAY, registry_path=path)["unattributed_fills"] == 1


@pytest.mark.parametrize("bad", [
    {**fill(), "fee": {"currency": "BNB", "cost": "0.1"}},
    {**fill(), "info": {}},
    {**fill(), "timestamp": TS - 86400000},
    {**fill(), "id": None},
])
def test_malformed_evidence_fails_closed(tmp_path, bad):
    with pytest.raises(ValueError):
        report(Demo([bad]), DAY, registry_path=tmp_path / "missing")


def test_duplicate_fills_fail_closed(tmp_path):
    with pytest.raises(ValueError, match="duplicate_fill"):
        report(Demo([fill(), fill()]), DAY, registry_path=tmp_path / "missing")


def test_rejects_live_endpoint(tmp_path):
    exchange = Demo([fill()])
    exchange.urls = {"api": {"fapiPrivate": "https://fapi.binance.com/fapi/v1"}}
    with pytest.raises(RuntimeError):
        report(exchange, DAY, registry_path=tmp_path / "missing")
