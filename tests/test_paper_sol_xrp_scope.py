"""SOL/XRP-only paper portfolio: isolation and fail-closed regression tests."""
import json
from decimal import Decimal as D

from futures_engine.__main__ import approve_paper_portfolio_entry
from futures_engine.paper import PaperLedger


def active_ledgers(root):
    for coin in ("sol", "xrp"):
        ledger = PaperLedger(root / f"paper-ledger-{coin}.json", D("75"))
        ledger.roll_day(300000)


def request(root):
    return approve_paper_portfolio_entry(
        {"entry": "10", "max_estimated_loss": "0.25"}, D("1"), 2, root)


def test_sol_xrp_only_accepts_valid_150_portfolio(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_PORTFOLIO_COINS", "sol,xrp")
    active_ledgers(tmp_path)
    assert request(tmp_path) == (True, "approved_offline_only")


def test_sol_xrp_only_does_not_require_legacy_ledgers(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_PORTFOLIO_COINS", "sol,xrp")
    active_ledgers(tmp_path)
    (tmp_path / "paper-ledger-btc.json").write_text("{invalid")
    (tmp_path / "paper-ledger-eth.json").write_text("{invalid")
    assert request(tmp_path) == (True, "approved_offline_only")


def test_sol_xrp_only_rejects_missing_active_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_PORTFOLIO_COINS", "sol,xrp")
    active_ledgers(tmp_path)
    (tmp_path / "paper-ledger-xrp.json").unlink()
    assert request(tmp_path) == (False, "portfolio_state_unavailable")


def test_sol_xrp_only_rejects_forged_profit(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_PORTFOLIO_COINS", "sol,xrp")
    active_ledgers(tmp_path)
    path = tmp_path / "paper-ledger-sol.json"
    state = json.loads(path.read_text())
    state["equity"] = "150"
    path.write_text(json.dumps(state))
    assert request(tmp_path) == (False, "portfolio_state_unavailable")


def test_sol_xrp_only_rejects_daily_loss(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_PORTFOLIO_COINS", "sol,xrp")
    active_ledgers(tmp_path)
    for coin in ("sol", "xrp"):
        path = tmp_path / f"paper-ledger-{coin}.json"
        state = json.loads(path.read_text())
        state["equity"] = "71"
        path.write_text(json.dumps(state))
    allowed, reason = request(tmp_path)
    assert not allowed and reason == "daily_loss_limit"


def test_invalid_paper_portfolio_coin_scope_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_PORTFOLIO_COINS", "btc,sol")
    active_ledgers(tmp_path)
    assert request(tmp_path) == (False, "portfolio_state_unavailable")
