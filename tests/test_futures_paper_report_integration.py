"""Integration smoke: real paper ledger entry/exit writes feed the report CLI.

Uses deterministic synthetic candles, not exchange data or live trading.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

from futures_engine.core import Config, plan_trade
from futures_engine.paper import locked_ledger


class PaperLedgerReportIntegration(unittest.TestCase):
    def test_persisted_entries_exits_and_report_cli(self):
        duration = 900000
        start = 1800000000000
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'paper-ledger.json'
            with locked_ledger(path, D('150'), 'BTC/USDT:USDT', '15m', duration) as ledger:
                ledger.roll_day(start)
                first = plan_trade(Config(), 'long', 100, ledger.state['equity'],
                                   ledger.state['day_start_equity'])
                ledger.open_position(first, start)
                exit1 = ledger.evaluate_exit(
                    [[start + duration, 100, 105, 99, 104, 10]],
                    D('0.0006'), D('0.0005'))
                self.assertEqual(exit1['reason'], 'target')
                second = plan_trade(Config(), 'short', 100, ledger.state['equity'],
                                    ledger.state['day_start_equity'])
                ledger.open_position(second, start + duration)
                exit2 = ledger.evaluate_exit(
                    [[start + 2 * duration, 100, 103, 99, 102, 10]],
                    D('0.0006'), D('0.0005'))
                self.assertEqual(exit2['reason'], 'stop')

            original = path.read_bytes()
            result = subprocess.run(
                [sys.executable, '-m', 'futures_engine.report', str(path)],
                capture_output=True, text=True, check=True)
            report = json.loads(result.stdout)
            persisted = json.loads(path.read_text())
            self.assertEqual(len(persisted['history']), 4)
            self.assertEqual(report['closed_trades'], 2)
            self.assertEqual(report['wins'], 1)
            self.assertEqual(report['losses'], 1)
            self.assertTrue(report['equity_reconciled'])
            self.assertEqual(report['mode'], 'paper_only')
            self.assertEqual(report['current_equity_usdt'], persisted['equity'])
            self.assertEqual(path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
