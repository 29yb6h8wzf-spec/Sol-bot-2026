"""Offline integration: actual PaperLedger writes -> exit -> read-only report CLI.

This is a deterministic fixture, NOT a market-data or production E2E run.
No credentials, network access, or live trading.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from futures_engine.paper import PaperLedger
from futures_engine.report import summarize_paper_ledger


class PaperLedgerReportIntegrationTests(unittest.TestCase):
    def test_persisted_entry_exit_and_cli_report(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "paper-ledger.json"
            paper = PaperLedger(path, initial_equity=Decimal("150"))
            paper.bind("BTCUSDT", "5m", 300000)
            plan = {
                "side": "long", "entry": "100", "stop": "99",
                "target": "102", "quantity": "1",
                "fee_rate": "0.001", "slippage_rate": "0",
            }
            paper.open_position(plan, 1000000)
            self.assertEqual(len(json.loads(path.read_text())["history"]), 1)
            exit_event = paper.evaluate_exit(
                [[1300000, 100, 103, 100, 101, 1]],
                Decimal("0.001"), Decimal("0"),
            )
            self.assertEqual(exit_event["reason"], "target")
            self.assertIsNone(paper.state["position"])
            self.assertEqual(len(paper.state["history"]), 2)
            self.assertEqual(exit_event["pnl"], "1.798")
            persisted = path.read_bytes()
            report = summarize_paper_ledger(json.loads(persisted))
            self.assertEqual(report["closed_trades"], 1)
            self.assertEqual(report["net_realized_pnl_usdt"], "1.798")
            self.assertEqual(report["modeled_costs_usdt"], "0.202")
            self.assertTrue(report["equity_reconciled"])
            completed = subprocess.run(
                [sys.executable, "-m", "futures_engine.report", str(path)],
                capture_output=True, text=True, check=True,
            )
            self.assertEqual(json.loads(completed.stdout), report)
            self.assertEqual(path.read_bytes(), persisted)


if __name__ == "__main__":
    unittest.main()
