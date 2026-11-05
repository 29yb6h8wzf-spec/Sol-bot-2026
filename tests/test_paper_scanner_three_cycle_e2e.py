"""Isolated three-cycle Paper scanner lifecycle; no exchange calls or real ledgers."""
import io
import json
from contextlib import redirect_stdout
from decimal import Decimal, ROUND_DOWN

from futures_engine import __main__ as scanner
from futures_engine.paper import PaperLedger


class MockExchange:
    def amount_to_precision(self, symbol, amount):
        return str(Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_DOWN))

    def close(self):
        pass


def test_three_scans_entry_target_exit_no_duplicate(tmp_path, monkeypatch):
    for coin in ("btc", "eth", "sol", "xrp"):
        PaperLedger(tmp_path / f"paper-ledger-{coin}.json",
                    Decimal("37.50")).roll_day(300000)
    cycle = {"scan": 0}
    ledger_path = tmp_path / "paper-ledger-sol.json"

    def market(*args):
        bars = [[300000, 100, 101, 99, 100, 10]]
        if cycle["scan"] > 0:
            bars.append([1200000, 100, 105, 99, 104, 10])
        return (MockExchange(),
                {"limits": {"amount": {"min": 0.01}, "cost": {"min": 5}}},
                bars)

    approve = scanner.approve_paper_portfolio_entry

    def approve_isolated(plan, amount, leverage):
        return approve(plan, amount, leverage, tmp_path)

    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.setenv("FUTURES_SYMBOL", "SOL/USDT:USDT")
    monkeypatch.setenv("TIMEFRAME", "15m")
    monkeypatch.setenv("PAPER_START_EQUITY", "37.50")
    monkeypatch.setenv("PAPER_LEDGER", str(ledger_path))
    monkeypatch.setenv("LEVERAGE", "2")
    monkeypatch.setattr(scanner, "closed_futures_bars", market)
    monkeypatch.setattr(
        scanner, "crossover_signal",
        lambda bars: "long" if cycle["scan"] == 0 else None)
    monkeypatch.setattr(
        scanner, "approve_paper_portfolio_entry", approve_isolated)

    for scan in range(3):
        cycle["scan"] = scan
        output = io.StringIO()
        with redirect_stdout(output):
            scanner.main()
        result = json.loads(output.getvalue())
        ledger = PaperLedger(ledger_path)
        if scan == 0:
            assert result["entry"] is not None
            assert ledger.state["position"] is not None
            assert len(ledger.state["history"]) == 1
            assert ledger.state["equity"] == "37.50"
        elif scan == 1:
            assert result["entry"] is None
            assert result["exit"]["reason"] == "target"
            assert ledger.state["position"] is None
            assert len(ledger.state["history"]) == 2
            assert Decimal(ledger.state["equity"]) == Decimal("38.10409600")
        else:
            assert result["entry"] is None
            assert result["exit"] is None
            assert ledger.state["position"] is None
            assert len(ledger.state["history"]) == 2
            assert Decimal(ledger.state["equity"]) == Decimal("38.10409600")
