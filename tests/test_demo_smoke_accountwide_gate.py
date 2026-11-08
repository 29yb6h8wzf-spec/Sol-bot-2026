"""Offline checks: account-wide demo smoke gate must refuse unrelated exposure."""
import pytest
from unittest.mock import patch
import signalpilot_demo_bracket_test as smoke

class FakeExchange:
    def __init__(self, *, positions=None, orders=None, algos=None):
        self.positions=positions or []
        self.orders=orders or []
        self.algos=algos or []
        self.options={}
        self.urls={"api":{"fapiPrivate":"https://demo-fapi.binance.com"}}
        self.entry_attempts=0
    def load_markets(self): pass
    def fetch_positions(self, symbols=None):
        if symbols: return [p for p in self.positions if p.get("symbol") in symbols]
        return self.positions
    def fetch_open_orders(self, symbol=None):
        if symbol: return [o for o in self.orders if o.get("symbol")==symbol]
        return self.orders
    def fapiPrivateGetOpenAlgoOrders(self, params):
        if params.get("symbol"): return [o for o in self.algos if o.get("symbol")==params["symbol"]]
        return self.algos
    def market_id(self,symbol): return "XRPUSDT"
    def fetch_position_mode(self,symbol): return {"hedged":False}
    def create_order(self,*args,**kwargs): self.entry_attempts+=1; raise AssertionError("entry must not occur")

@pytest.mark.parametrize("kind",["positions","orders","algos"])
def test_other_symbol_activity_blocks_before_entry(monkeypatch,kind):
    items={"positions":[{"symbol":"BTC/USDT:USDT","contracts":"0.1","side":"long"}],
           "orders":[{"symbol":"BTC/USDT:USDT"}],
           "algos":[{"symbol":"BTCUSDT","algoId":42}]}
    exchange=FakeExchange(**{kind:items[kind]})
    monkeypatch.setenv("DEMO_TEST_CONFIRM","YES")
    monkeypatch.setattr(smoke,"demo_exchange",lambda:exchange)
    with pytest.raises(RuntimeError,match="account-wide"):
        smoke.main()
    assert exchange.entry_attempts==0


def test_missing_confirmation_never_loads_demo_credentials(monkeypatch):
    monkeypatch.delenv("DEMO_TEST_CONFIRM",raising=False)
    monkeypatch.setattr(smoke,"demo_exchange",lambda: (_ for _ in ()).throw(AssertionError("must not connect")))
    assert smoke.main()==0
