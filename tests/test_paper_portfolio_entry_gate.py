"""Portfolio limits are enforced at the scanner entry boundary (paper only)."""
import json
from decimal import Decimal
from types import SimpleNamespace
from futures_engine import __main__ as scanner


def states(root, *, equity="37.50", day_start="37.50", position=None):
    for coin in ("btc", "eth", "sol", "xrp"):
        (root / f"paper-ledger-{coin}.json").write_text(json.dumps({
            "equity": equity, "day_start_equity": day_start,
            "position": position if coin == "btc" else None
        }))


def test_portfolio_entry_approved_with_free_budget(tmp_path):
    states(tmp_path)
    result = scanner.approve_paper_portfolio_entry(
        {"entry": "100", "max_estimated_loss": "1.20"},
        Decimal("1"), 2, tmp_path)
    assert result == (True, "approved_offline_only")


def test_portfolio_entry_blocks_shared_margin(tmp_path):
    states(tmp_path, position={"margin_estimate": "135", "max_estimated_loss": "1"})
    allowed, reason = scanner.approve_paper_portfolio_entry(
        {"entry": "100", "max_estimated_loss": "1.20"},
        Decimal("1"), 2, tmp_path)
    assert not allowed and reason == "insufficient_margin"


def test_portfolio_entry_blocks_daily_loss(tmp_path):
    states(tmp_path, equity="35.625", day_start="37.50")
    allowed, reason = scanner.approve_paper_portfolio_entry(
        {"entry": "100", "max_estimated_loss": "1.20"},
        Decimal("1"), 2, tmp_path)
    assert not allowed and reason == "daily_loss_limit"


def test_portfolio_entry_blocks_missing_or_corrupt_ledger(tmp_path):
    assert scanner.approve_paper_portfolio_entry(
        {"entry": "100", "max_estimated_loss": "1.20"},
        Decimal("1"), 2, tmp_path) == (False, "portfolio_state_unavailable")
    states(tmp_path)
    (tmp_path / "paper-ledger-sol.json").write_text("{broken")
    assert scanner.approve_paper_portfolio_entry(
        {"entry": "100", "max_estimated_loss": "1.20"},
        Decimal("1"), 2, tmp_path) == (False, "portfolio_state_unavailable")


def test_scanner_never_opens_paper_entry_when_portfolio_blocks(monkeypatch, capsys):
    import os
    monkeypatch.setenv("TRADING_MODE", "paper")
    ledger=SimpleNamespace(
        state={"equity": "37.50", "day_start_equity": "37.50",
               "position": None, "last_signal_candle": None},
        roll_day=lambda ts: None,
        evaluate_exit=lambda *args: None,
        open_position=lambda *args: (_ for _ in ()).throw(AssertionError("entry attempted")))
    class FakeExchange:
        def amount_to_precision(self, symbol, amount): return amount
        def close(self): pass
    exchange=FakeExchange()
    monkeypatch.setattr(scanner, "PaperLedger", lambda *args, **kwargs: ledger)
    monkeypatch.setattr(scanner, "closed_futures_bars", lambda *args: (
        exchange, {"limits": {"amount": {"min": 0.001}, "cost": {"min": 1}}},
        [[300000, 100, 100, 100, 100, 10]]))
    monkeypatch.setattr(scanner, "crossover_signal", lambda bars: "long")
    monkeypatch.setattr(scanner, "plan_trade", lambda *args, **kwargs: {
        "entry": "100", "quantity": "1", "max_estimated_loss": "1.2"})
    monkeypatch.setattr(scanner, "approve_paper_portfolio_entry",
                        lambda *args, **kwargs: (False, "daily_loss_limit"))
    scanner.main()
    result=json.loads(capsys.readouterr().out)
    assert result["entry"] is None
    assert result["portfolio_block"] == "daily_loss_limit"
