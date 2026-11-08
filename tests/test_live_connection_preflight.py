"""Read-only Binance live connection inspection regression tests."""
import pytest
from live_connection_preflight import inspect


class Exchange:
    urls = {"api": {"fapiPrivate": "https://fapi.binance.com"}}
    def __init__(self, positions=None, orders=0, algos=0, hedged=False):
        self.positions, self.orders, self.algos, self.hedged = positions or [], orders, algos, hedged
        self.calls = []
        self.options = {}
    def load_markets(self): self.calls.append("load")
    def fetch_position_mode(self): return {"hedged": self.hedged}
    def fetch_positions(self, symbols=None): return self.positions
    def fetch_open_orders(self, symbol=None): return [{}] * self.orders
    def market_id(self, symbol): return symbol.replace("/USDT:USDT", "USDT")
    def fapiPrivateGetOpenAlgoOrders(self, args): return [{"algoId": i} for i in range(self.algos)]


def test_flat_read_only_preflight():
    exchange = Exchange()
    report = inspect(exchange)
    assert exchange.options["fetchOpenOrders"]["warnWithoutSymbol"] is False
    assert report["account_flat"]
    assert report["account_wide_algo_inventory_verified"] is True
    assert report["all_order_inventory_verified"] is True
    assert report["ready_for_live_trading"] is False
    assert report["status"] == "LIVE_CONNECTION_READ_ONLY_FULL_INVENTORY"
    assert not report["execution_authorized"]
    assert not report["orders_sent"]


@pytest.mark.parametrize("kwargs", [
    {"positions": [{"symbol": "XRP/USDT:USDT", "contracts": 1}]},
    {"positions": [{"symbol": "BNB/USDT:USDT", "contracts": 2}]},
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


def test_unrecognized_algo_response_fails_closed():
    exchange = Exchange()
    exchange.fapiPrivateGetOpenAlgoOrders = lambda args: {"unexpected": "response"}
    with pytest.raises(ValueError, match="invalid_account_wide_algo_inventory"):
        inspect(exchange)


def test_account_wide_algo_query_has_no_symbol():
    exchange = Exchange()
    calls = []
    def query(args):
        calls.append(args)
        return []
    exchange.fapiPrivateGetOpenAlgoOrders = query
    inspect(exchange)
    assert calls == [{}]


def test_account_wide_algo_detects_other_symbol():
    exchange = Exchange()
    exchange.fapiPrivateGetOpenAlgoOrders = lambda args: [{"symbol": "BNBUSDT", "algoId": 123}]
    with pytest.raises(ValueError, match="existing_exposure_or_orders"):
        inspect(exchange)


def test_account_wide_algo_rejects_invalid_shape():
    exchange = Exchange()
    exchange.fapiPrivateGetOpenAlgoOrders = lambda args: {"orders": None}
    with pytest.raises(ValueError, match="invalid_account_wide_algo_inventory"):
        inspect(exchange)
