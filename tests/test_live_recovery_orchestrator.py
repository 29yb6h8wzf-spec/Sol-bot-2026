import pytest
from live_recovery_orchestrator import recover_possible_entry, CriticalRecoveryError


class Journal:
    def __init__(self): self.states = []
    def mark(self, signal_id, state): self.states.append(state)


class Exchange:
    def __init__(self, fail=False):
        self.position = 1
        self.fail = fail
        self.calls = []
    def fetch_positions(self, symbols):
        return [{"symbol": symbols[0], "side": "long", "contracts": str(self.position)}]
    def create_order(self, *args):
        self.calls.append("flatten")
        if self.fail: raise TimeoutError("order result unknown")
        self.position = 0
    def market_id(self, symbol): return "XRPUSDT"
    def fapiPrivateDeleteAlgoOpenOrders(self, args): self.calls.append("cancel_algo")
    def cancel_all_orders(self, symbol): self.calls.append("cancel_orders")
    def fetch_open_orders(self, symbol): return []
    def fapiPrivateGetOpenAlgoOrders(self, args): return []


def test_recovery_verified_before_protections_removed():
    exchange, journal = Exchange(), Journal()
    recover_possible_entry(exchange, "XRP/USDT:USDT", "id1", journal)
    assert exchange.calls == ["flatten", "cancel_algo", "cancel_orders"]
    assert journal.states[-1] == "RECOVERY_VERIFIED_FLAT"


def test_timeout_requires_manual_intervention_and_preserves_protection():
    exchange, journal = Exchange(fail=True), Journal()
    with pytest.raises(CriticalRecoveryError):
        recover_possible_entry(exchange, "XRP/USDT:USDT", "id1", journal)
    assert exchange.calls == ["flatten"] * 3
    assert journal.states[-1].startswith("CRITICAL_")
