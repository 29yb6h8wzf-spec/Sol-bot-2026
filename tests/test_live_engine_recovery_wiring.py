"""Offline-only live executor recovery wiring tests; no credentials or network."""
from decimal import Decimal
import pytest
import futures_engine.live as live

class Journal:
    def __init__(self): self.events=[]
    def claim(self, sid): return True
    def mark(self, sid, status): self.events.append(status)

class Exchange:
    def __init__(self, *, timeout=False, bracket_fail=False, flatten_fail=False):
        self.timeout=timeout; self.bracket_fail=bracket_fail; self.flatten_fail=flatten_fail
        self.position=0; self.events=[]
    def check_required_credentials(self): return True
    def fetch_positions(self, symbols):
        return [{"symbol":symbols[0],"contracts":self.position,"side":"long"}]
    def fetch_open_orders(self, symbol): return []
    def fapiPrivateGetOpenAlgoOrders(self, args): return []
    def market_id(self, symbol): return "BTCUSDT"
    def market(self, symbol): return {"linear":True,"swap":True,"active":True,"limits":{"amount":{"min":0.001},"cost":{"min":5}}}
    def amount_to_precision(self, symbol, amount): return amount
    def fetch_position_mode(self, symbol=None): return {"hedged":False}
    def set_leverage(self, leverage, symbol): pass
    def create_order(self, symbol, kind, side, qty, price, params):
        if params.get("reduceOnly"):
            self.events.append("flatten")
            if self.flatten_fail: raise TimeoutError("simulated flatten failure")
            self.position=0
            return {"id":"exit"}
        self.position=qty
        self.events.append("entry")
        if self.timeout: raise TimeoutError("simulated lost entry ack")
        return {"id":"entry"}
    def fapiPrivatePostAlgoOrder(self, args):
        self.events.append("algo")
        if self.bracket_fail: raise TimeoutError("simulated bracket failure")
        return {"algoId":1}
    def fapiPrivateDeleteAlgoOpenOrders(self, args):
        assert self.position==0
        self.events.append("cleanup_algo")
    def cancel_all_orders(self, symbol):
        assert self.position==0
        self.events.append("cleanup_orders")

@pytest.fixture(autouse=True)
def armed_offline(monkeypatch):
    monkeypatch.setattr(live,"require_live_arming",lambda:None)
    monkeypatch.setenv("BINANCE_BRACKET_CERTIFIED","YES_TESTNET_VERIFIED")


def intent():
    return live.TradeIntent("BTC/USDT:USDT","long",85,"verified_85_score_engine",
        Decimal("100"),Decimal("99"),Decimal("102"),Decimal("0.1"),"sig1")

ACCOUNT={"equity":Decimal("150"),"day_start_equity":Decimal("150")}

@pytest.mark.parametrize("kind",["timeout","bracket_fail"])
def test_entry_or_bracket_failure_recovers_before_cleanup(kind):
    x,j=Exchange(**{kind:True}),Journal()
    with pytest.raises(live.LiveSafetyError,match="verified flat"):
        live.execute_protected_entry(x,intent(),journal=j,account=ACCOUNT)
    assert x.events.index("flatten") < x.events.index("cleanup_algo")
    assert x.position==0
    assert j.events[-1]=="RECOVERY_VERIFIED_FLAT"


def test_flatten_failure_preserves_orders_and_halts():
    x,j=Exchange(timeout=True,flatten_fail=True),Journal()
    with pytest.raises(live.LiveSafetyError,match="HALT ALL ENTRIES"):
        live.execute_protected_entry(x,intent(),journal=j,account=ACCOUNT)
    assert "cleanup_algo" not in x.events
    assert "cleanup_orders" not in x.events
    assert j.events[-1].startswith("CRITICAL_RECOVERY_INCOMPLETE")
