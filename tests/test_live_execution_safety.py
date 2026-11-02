"""Offline live safety checks: no network or orders."""
from dataclasses import replace
from decimal import Decimal as D
import pytest
from futures_engine.live import TradeIntent, LiveSafetyError, validate_intent, require_live_arming, execute_protected_entry

GOOD = TradeIntent("SOL/USDT:USDT", "long", 90, "verified_85_score_engine",
                   D("100"), D("99"), D("102"), D("1"), "SOL-20261102-001")
ACCOUNT = {"equity": D("150"), "day_start_equity": D("150")}


def test_valid_offline_preflight():
    assert validate_intent(GOOD, **ACCOUNT)["estimated_loss"] < D("1.50")


@pytest.mark.parametrize("changes", [
    {"score": 84}, {"source": "Kraken Spot"}, {"symbol": "BNB/USDT:USDT"},
    {"stop": D("101")}, {"target": D("99")}, {"quantity": D("2")},
    {"signal_id": "../bad"}, {"entry": D("NaN")},
])
def test_rejects_bad_intents(changes):
    with pytest.raises(LiveSafetyError):
        validate_intent(replace(GOOD, **changes), **ACCOUNT)


def test_daily_loss_and_open_risk():
    with pytest.raises(LiveSafetyError):
        validate_intent(GOOD, equity=D("142.50"), day_start_equity=D("150"))
    with pytest.raises(LiveSafetyError):
        validate_intent(GOOD, **ACCOUNT, existing_risk=D("7"))


def test_live_disarmed_by_default(monkeypatch):
    monkeypatch.delenv("SIGNALPILOT_LIVE_ARMED", raising=False)
    monkeypatch.setenv("TRADING_MODE", "live")
    with pytest.raises(LiveSafetyError, match="disarmed"):
        require_live_arming()


def test_no_order_even_when_armed(monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "live")
    monkeypatch.setenv("SIGNALPILOT_LIVE_ARMED", "YES_I_ACCEPT_REAL_LOSSES")
    class Exchange:
        def check_required_credentials(self): return True
        def fetch_positions(self, symbols): return []
        def fetch_open_orders(self, symbol): return []
        def market(self, symbol): return {"linear": True, "swap": True, "active": True, "limits": {}}
        def amount_to_precision(self, symbol, amount): return amount
        def create_order(self, *args, **kwargs): raise AssertionError("MUST NOT PLACE ORDER")
    class Journal:
        def claim(self, key): return True
        def mark(self, key, state): pass
    with pytest.raises(LiveSafetyError, match="not certified"):
        execute_protected_entry(Exchange(), GOOD, journal=Journal(), account=ACCOUNT)


def test_mock_live_bracket_lifecycle(monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "live")
    monkeypatch.setenv("SIGNALPILOT_LIVE_ARMED", "YES_I_ACCEPT_REAL_LOSSES")
    monkeypatch.setenv("BINANCE_BRACKET_CERTIFIED", "YES_TESTNET_VERIFIED")
    class Exchange:
        def __init__(self):
            self.orders = []
            self.position = D("0")
        def check_required_credentials(self): return True
        def fetch_positions(self, symbols): return [{"symbol": GOOD.symbol, "contracts": str(self.position)}]
        def fetch_open_orders(self, symbol): return self.orders
        def market(self, symbol): return {"linear": True, "swap": True, "active": True, "limits": {}}
        def amount_to_precision(self, symbol, amount): return amount
        def fetch_position_mode(self, symbol): return {"hedged": False}
        def set_leverage(self, value, symbol): assert value == 2
        def create_order(self, symbol, kind, side, amount, price, params):
            if kind == "market":
                self.position = D(str(amount))
            order = {"id": str(len(self.orders) + 1), "type": kind}
            if kind != "market": self.orders.append(order)
            return order
    class Journal:
        def __init__(self): self.claimed = set(); self.states = []
        def claim(self, key):
            if key in self.claimed: return False
            self.claimed.add(key)
            return True
        def mark(self, key, state): self.states.append(state)
    exchange, journal = Exchange(), Journal()
    result = execute_protected_entry(exchange, GOOD, journal=journal, account=ACCOUNT)
    assert result["stop"]["type"] == "STOP_MARKET"
    assert result["target"]["type"] == "TAKE_PROFIT_MARKET"
    assert journal.states[-1] == "PROTECTED"
    with pytest.raises(LiveSafetyError, match="duplicate"):
        execute_protected_entry(exchange, GOOD, journal=journal, account=ACCOUNT)
