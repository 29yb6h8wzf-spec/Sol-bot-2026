"""Unit tests for single-source 5m offline score replay."""
import unittest
from unittest.mock import patch

from futures_engine.research_five_minute_score_replay_cli import report_from_five_minute


def candles(n):
    return [[i * 300000, 100, 101, 99, 100, 10] for i in range(n)]


class FiveMinuteReplayTests(unittest.TestCase):
    def test_closed_4h_derived_and_reported(self):
        data = candles(48 * 101)
        with patch("futures_engine.research_five_minute_score_replay_cli.replay_report",
                   return_value={"totals": {"scans": 2, "setups": 0}}) as run:
            result = report_from_five_minute({"SOL/USDT:USDT": data}, cutoff_ms=48 * 101 * 300000)
        self.assertEqual(result["totals"]["scans"], 2)
        prepared = run.call_args.args[0]["SOL/USDT:USDT"]
        self.assertEqual(len(prepared["4h"]), 101)
        self.assertEqual(prepared["4h"][-1][0], 100 * 14400000)

    def test_incomplete_4h_history_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "insufficient_4h_history"):
            report_from_five_minute({"XRP/USDT:USDT": candles(48 * 99 + 47)}, cutoff_ms=48 * 100 * 300000)

    def test_unsupported_symbol_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "invalid_symbols"):
            report_from_five_minute({"BTC/USDT:USDT": candles(48 * 101)}, cutoff_ms=48 * 101 * 300000)

    def test_future_candles_excluded(self):
        data = candles(48 * 101 + 5)
        with patch("futures_engine.research_five_minute_score_replay_cli.replay_report",
                   return_value={"totals": {"scans": 2, "setups": 0}}) as run:
            report_from_five_minute({"SOL/USDT:USDT": data},
                                    cutoff_ms=48 * 101 * 300000)
        self.assertEqual(len(run.call_args.args[0]["SOL/USDT:USDT"]["5m"]), 48 * 101)

    def test_cutoff_must_be_utc_five_minute_boundary(self):
        with self.assertRaisesRegex(ValueError, "invalid_utc_cutoff"):
            report_from_five_minute({"SOL/USDT:USDT": candles(48 * 101)},
                                    cutoff_ms=48 * 101 * 300000 + 1)

    def test_gap_fails_closed(self):
        data = candles(48 * 101)
        data[10][0] += 300000
        with self.assertRaises(ValueError):
            report_from_five_minute({"SOL/USDT:USDT": data}, cutoff_ms=48 * 101 * 300000)


if __name__ == "__main__":
    unittest.main()
