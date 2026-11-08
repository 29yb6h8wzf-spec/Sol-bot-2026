"""Live recovery integration contract: no real credentials or orders."""
import pytest
from live_recovery_orchestrator import recover_possible_entry, CriticalRecoveryError


class Journal:
    def __init__(self): self.events = []
    def mark(self, signal_id, state): self.events.append((signal_id, state))


class Exchange:
    def __init__(self, *, fail_flatten=False):
        self.position = 1
        self.fail_flatten = fail_flatten
        self.events = []
    def fetch_positions(self, symbols):
        return [{"symbol": symbols[0], "contracts": self.position, "side": "long"}]
    def create_order(self, symbol, kind, side, qty, price, params):
        assert kind == "market" and side == "sell" and params == {"reduceOnly": True}
        self.events.append("flatten")
        if self.fail_flatten: raise TimeoutError("simulated network timeout")
        self.position = 0
    def market_id(self, symbol): return "BTCUSDT"
    def fapiPrivateDeleteAlgoOpenOrders(self, args):
        assert self.position == 0
        self.events.append("cancel_algos")
    def cancel_all_orders(self, symbol):
        assert self.position == 0
        self.events.append("cancel_orders")
    def fetch_open_orders(self, symbol): return []
    def fapiPrivateGetOpenAlgoOrders(self, args): return []


def test_ambiguous_entry_recovery_flattens_before_cleanup():
    exchange, journal = Exchange(), Journal()
    assert recover_possible_entry(exchange, "BTC/USDT:USDT", "sig1", journal)["status"] == "FLAT_AND_CLEAN_VERIFIED"
    assert exchange.events == ["flatten", "cancel_algos", "cancel_orders"]
    assert journal.events[-1] == ("sig1", "RECOVERY_VERIFIED_FLAT")


def test_failed_flatten_preserves_protection_and_escalates():
    exchange, journal = Exchange(fail_flatten=True), Journal()
    with pytest.raises(CriticalRecoveryError, match="halt all entries"):
        recover_possible_entry(exchange, "BTC/USDT:USDT", "sig2", journal)
    assert "cancel_algos" not in exchange.events
    assert "cancel_orders" not in exchange.events
    assert journal.events[-1][1].startswith("CRITICAL_RECOVERY_INCOMPLETE")
