"""Offline-only integration checks for ambiguous Binance entry acknowledgements."""
import pytest
from live_execution_recovery_guard import submit_with_recovery, EntryRecoveryRequired
from live_recovery_orchestrator import CriticalRecoveryError

class Journal:
    def __init__(self): self.events=[]
    def mark(self, sid, state): self.events.append(state)

class Exchange:
    def __init__(self, fail=False): self.position=1; self.fail=fail; self.events=[]
    def fetch_positions(self, symbols): return [{"symbol":symbols[0],"contracts":self.position,"side":"long"}]
    def create_order(self, symbol, kind, side, qty, price, params):
        assert params == {"reduceOnly":True}
        self.events.append("flatten")
        if self.fail: raise TimeoutError("offline simulated timeout")
        self.position=0
    def market_id(self, symbol): return "BTCUSDT"
    def fapiPrivateDeleteAlgoOpenOrders(self, args):
        assert self.position==0
        self.events.append("cleanup_algo")
    def cancel_all_orders(self, symbol):
        assert self.position==0
        self.events.append("cleanup_orders")
    def fetch_open_orders(self, symbol): return []
    def fapiPrivateGetOpenAlgoOrders(self, args): return []


def test_timeout_after_possible_fill_recovers_before_cleanup():
    x,j=Exchange(),Journal()
    def timeout(): raise TimeoutError("ack lost")
    with pytest.raises(EntryRecoveryRequired):
        submit_with_recovery(x,"BTC/USDT:USDT","s1",j,timeout)
    assert x.events==["flatten","cleanup_algo","cleanup_orders"]
    assert j.events[-1]=="RECOVERY_VERIFIED_FLAT"


def test_unresolved_flatten_halts_without_removing_protection():
    x,j=Exchange(fail=True),Journal()
    def timeout(): raise TimeoutError("ack lost")
    with pytest.raises(CriticalRecoveryError):
        submit_with_recovery(x,"BTC/USDT:USDT","s2",j,timeout)
    assert x.events==["flatten"]*3
    assert j.events[-1].startswith("CRITICAL_RECOVERY_INCOMPLETE")


def test_success_does_not_call_recovery():
    x,j=Exchange(),Journal()
    assert submit_with_recovery(x,"BTC/USDT:USDT","s3",j,lambda:{"id":"ok"})=={"id":"ok"}
    assert x.events==[]
    assert j.events==["ENTRY_SUBMITTING","ENTRY_ACKNOWLEDGED"]
