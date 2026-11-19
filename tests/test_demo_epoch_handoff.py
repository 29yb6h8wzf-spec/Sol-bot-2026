"""No-network regression for Demo epoch -> independently verified execution gate."""
import sqlite3
import pytest
import demo_epoch_handoff as bridge
from demo_execution_gate import DemoGateBlocked
from test_demo_execution_gate import evidence, NOW


class GetOnlyDemo:
    _signalpilot_get_only_guard = True
    def create_order(self, *args, **kwargs):
        raise AssertionError("no exchange order permitted")


def install(monkeypatch):
    signal, verified, route, plan, account = evidence()
    monkeypatch.setattr(bridge, "read_snapshot", lambda ex, sym, now=None: account)
    monkeypatch.setattr(bridge, "closed_bars", lambda ex, sym, candle: ["closed"])
    monkeypatch.setattr(bridge, "market_filters",
                        lambda ex, sym: ("0.01", "0.001", "0.001", "5"))
    monkeypatch.setattr(bridge, "plan_bracket", lambda *a, **kw: plan)
    monkeypatch.setattr(bridge, "preflight_with_epoch", lambda *a, **kw: (True, "ok"))
    return signal, verified, plan


def test_complete_offline_handoff_and_reservation(monkeypatch, tmp_path):
    signal, verified, plan = install(monkeypatch)
    result = bridge.prepare(signal, GetOnlyDemo(), now=NOW,
                            verifier=lambda payload: verified)
    assert result["intent"]["notional"] == "10.0"
    assert result["orders_sent"] is False
    db = tmp_path / "journal.db"
    intent = bridge.reserve_handoff(db, result, now=NOW)
    assert intent["event_key"] == result["intent"]["event_key"]
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT state FROM demo_execution_reservations").fetchone() == ("RESERVED_NO_ORDERS",)
    with pytest.raises(DemoGateBlocked, match="already_reserved"):
        bridge.reserve_handoff(db, result, now=NOW)


def test_rejects_without_transport_guard(monkeypatch):
    signal, verified, _ = install(monkeypatch)
    class Unguarded:
        pass
    with pytest.raises(DemoGateBlocked, match="guard_missing"):
        bridge.prepare(signal, Unguarded(), now=NOW,
                       verifier=lambda payload: verified)


def test_risk_block_does_not_reserve(monkeypatch, tmp_path):
    signal, verified, _ = install(monkeypatch)
    monkeypatch.setattr(bridge, "preflight_with_epoch",
                        lambda *a, **kw: (False, "epoch_risk_status_stale"))
    with pytest.raises(DemoGateBlocked, match="epoch_risk_blocked"):
        bridge.prepare(signal, GetOnlyDemo(), now=NOW,
                       verifier=lambda payload: verified)
    assert not (tmp_path / "journal.db").exists()


def test_no_candidate_fails_closed(monkeypatch):
    signal, verified, _ = install(monkeypatch)
    with pytest.raises(DemoGateBlocked, match="independent_verification_failed"):
        bridge.prepare(signal, GetOnlyDemo(), now=NOW,
                       verifier=lambda payload: None)


def test_rejects_untrusted_verified_market(monkeypatch):
    signal, verified, _ = install(monkeypatch)
    verified["symbol"] = "BTC/USDT:USDT"
    with pytest.raises(DemoGateBlocked, match="unsupported_demo_symbol"):
        bridge.prepare(signal, GetOnlyDemo(), now=NOW,
                       verifier=lambda payload: verified)


def test_handoff_does_not_call_broker_post():
    import inspect
    source = inspect.getsource(bridge)
    assert "create_order(" not in source
    assert "fapiPrivatePost" not in source
