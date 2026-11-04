import pytest
from demo_historical_inventory import inventory


class FakeExchange:
    urls = {"api": {"fapiPrivate": "https://demo-fapi.binance.com"}}

    def __init__(self, trades=None):
        self.trades = trades or []
        self.calls = []

    def fetch_my_trades(self, symbol, *, since, limit):
        self.calls.append((symbol, since, limit))
        return [x for x in self.trades if x["symbol"] == symbol and x["timestamp"] >= since]


def test_empty_history_is_not_reconciled():
    exchange = FakeExchange()
    result = inventory(exchange, "2026-11-01", "2026-11-02")
    assert len(exchange.calls) == 8
    assert all(day["complete_account_coverage"] is False for day in result["days"])
    assert all(len(day["fills_by_symbol"]) == 4 for day in result["days"])
    assert result["historical_reconciliation_complete"] is False
    assert result["execution_authorized"] is False
    assert result["orders_sent"] is False


def test_counts_one_fill():
    exchange = FakeExchange([{"symbol": "BTC/USDT:USDT",
                              "timestamp": 1793491200000, "id": "12"}])
    result = inventory(exchange, "2026-11-01", "2026-11-01")
    assert result["days"][0]["observed_fills"] == 1
    assert result["days"][0]["fills_by_symbol"]["BTC/USDT:USDT"] == 1
    assert sum(result["days"][0]["fills_by_symbol"].values()) == 1


def test_full_page_fails_closed():
    exchange = FakeExchange([{"symbol": "BTC/USDT:USDT",
                              "timestamp": 1793491200000, "id": "12"}])
    with pytest.raises(ValueError, match="incomplete_historical_page"):
        inventory(exchange, "2026-11-01", "2026-11-01", limit=1)


def test_window_over_seven_days_rejected():
    with pytest.raises(ValueError, match="invalid_historical_window"):
        inventory(FakeExchange(), "2026-10-01", "2026-11-01")
