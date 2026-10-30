"""Offline regression tests for paper-only performance reporting."""
import unittest

from futures_engine.report import summarize_paper_ledger


def ledger(pnls=(), costs=(), equity='150', position=None):
    return {
        'equity': equity,
        'day_start_equity': '150',
        'position': position,
        'history': [
            {'event': 'paper_exit', 'pnl': str(p), 'costs': str(c)}
            for p, c in zip(pnls, costs)
        ],
    }


class PaperReportTests(unittest.TestCase):
    def test_empty_ledger(self):
        report = summarize_paper_ledger(ledger())
        self.assertEqual(report['closed_trades'], 0)
        self.assertIsNone(report['win_rate_pct'])
        self.assertIsNone(report['profit_factor'])
        self.assertEqual(report['mode'], 'paper_only')

    def test_closed_trades_include_costs_and_drawdown(self):
        report = summarize_paper_ledger(ledger(
            pnls=('5', '-2', '-3', '4'), costs=('0.5', '0.4', '0.3', '0.2'), equity='154'))
        self.assertEqual(report['closed_trades'], 4)
        self.assertEqual(report['wins'], 2)
        self.assertEqual(report['losses'], 2)
        self.assertEqual(report['win_rate_pct'], '50.0')
        self.assertEqual(report['net_realized_pnl_usdt'], '4')
        self.assertEqual(report['modeled_costs_usdt'], '1.4')
        self.assertEqual(report['max_consecutive_losses'], 2)
        self.assertEqual(report['profit_factor'], '1.8')
        self.assertGreater(float(report['max_closed_equity_drawdown_pct']), 3.2)

    def test_open_position_does_not_count_as_realized(self):
        report = summarize_paper_ledger(ledger(position={'side': 'long', 'entry': '200'}))
        self.assertTrue(report['open_position'])
        self.assertFalse(report['unrealized_pnl_included'])
        self.assertEqual(report['net_realized_pnl_usdt'], '0')

    def test_invalid_equity_reconciliation_rejected(self):
        with self.assertRaises(ValueError):
            summarize_paper_ledger(ledger(pnls=('3',), costs=('0',), equity='150'))

    def test_nonfinite_values_rejected(self):
        with self.assertRaises(ValueError):
            summarize_paper_ledger(ledger(pnls=('NaN',), costs=('0',)))
        with self.assertRaises(ValueError):
            summarize_paper_ledger(ledger(pnls=('-1',), costs=('-1',), equity='149'))


if __name__ == '__main__':
    unittest.main()
