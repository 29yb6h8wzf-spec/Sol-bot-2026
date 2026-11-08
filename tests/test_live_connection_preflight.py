"""Read-only Binance live connection inspection regression tests."""
import pytest
from live_connection_preflight import inspect


class Exchange:
    urls = {"api": {"fapiPrivate": "https://fapi.binance.com"}}
    def __init__(self, positions=None, orders=0, algos=0, hedged=False):
        self.positions, self.orders, self.algos, self.hedged = positions or [], orders, algos, hedged
        self.calls = []
    def load_markets(self): self.calls.append("load")
    def fetch_position_mode(self): return {"hedged": self.hedged}
    def fetch_positions(self, symbols): return self.positions
    def fetch_open_orders(self, symbol): return [{}] * self.orders
    def market_id(self, symbol): return symbol.replace("/USDT:USDT", "USDT")
    def fapiPrivateGetOpenAlgoOrders(self, args): return [{"algoId": i} for i in range(self.algos)]


def test_flat_read_only_preflight():
    exchange = Exchange()
    report = inspect(exchange)
    assert report["account_flat"]
    assert not report["execution_authorized"]
    assert not report["orders_sent"]


@pytest.mark.parametrize("kwargs", [
    {"positions": [{"symbol": "XRP/USDT:USDT", "contracts": 1}]},
    {"orders": 1}, {"algos": 1}, {"hedged": True},
])
def test_preflight_blocks_exposure_orders_and_hedge(kwargs):
    with pytest.raises(ValueError):
        inspect(Exchange(**kwargs))


def test_preflight_rejects_demo():
    exchange = Exchange()
    exchange.urls = {"api": "https://demo-fapi.binance.com"}
    with pytest.raises(ValueError):
        inspect(exchange)
