from decimal import Decimal
import pytest
from live_emergency_recovery import flatten_then_cleanup, RecoveryIncomplete


class Exchange:
    def __init__(self, position="2", side="long", fail=False):
        self.position = Decimal(position)
        self.side = side
        self.fail = fail
        self.calls = []
    def fetch_positions(self, symbols):
        return [{"symbol": symbols[0], "side": self.side, "contracts": str(self.position)}]
    def create_order(self, symbol, kind, side, qty, price, params):
        self.calls.append("flatten")
        assert params == {"reduceOnly": True}
        assert side == ("sell" if self.side == "long" else "buy")
        if self.fail:
            raise TimeoutError("unknown outcome")
        self.position = Decimal("0")
    def market_id(self, symbol): return "XRPUSDT"
    def fapiPrivateDeleteAlgoOpenOrders(self, params): self.calls.append("cancel_algo")
    def cancel_all_orders(self, symbol): self.calls.append("cancel_regular")
    def fetch_open_orders(self, symbol): return []
    def fapiPrivateGetOpenAlgoOrders(self, params): return []


@pytest.mark.parametrize("side", ["long", "short"])
def test_flatten_before_cancel(side):
    e = Exchange(side=side)
    assert flatten_then_cleanup(e, "XRP/USDT:USDT")["status"] == "FLAT_AND_CLEAN_VERIFIED"
    assert e.calls == ["flatten", "cancel_algo", "cancel_regular"]


def test_timeout_preserves_protection():
    e = Exchange(fail=True)
    with pytest.raises(RecoveryIncomplete, match="preserved"):
        flatten_then_cleanup(e, "XRP/USDT:USDT")
    assert e.calls == ["flatten"] * 3


def test_flat_position_cleanup():
    e = Exchange(position="0")
    flatten_then_cleanup(e, "XRP/USDT:USDT")
    assert e.calls == ["cancel_algo", "cancel_regular"]
