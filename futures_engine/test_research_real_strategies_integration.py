"""Exercise the real strategies.candidates implementation, not a mock.

The first 100 closed 4h bars are needed for replay; 5m data covering only
five days is insufficient for the single-source replay.
"""
import unittest

from futures_engine.research_five_minute_score_replay_cli import report_from_five_minute


def make_five(count):
    # Deterministic, contiguous UTC 5m OHLCV, deliberately not market data.
    return [[i * 300000, 100.0, 101.0, 99.0, 100.0, 100.0]
            for i in range(count)]


class RealStrategiesReplayIntegrationTests(unittest.TestCase):
    def test_real_strategy_pipeline_without_mocks(self):
        # 101 complete 4h bars; 4848 5m bars; one valid replay scan
        candles = make_five(48 * 101)
        report = report_from_five_minute(
            {"SOL/USDT:USDT": candles},
            cutoff_ms=len(candles) * 300000,
        )
        self.assertEqual(report["totals"]["scans"], 1)
        self.assertEqual(report["totals"]["no_setup_scans"], 1)
        self.assertEqual(report["totals"].get("setups", 0), 0)
        self.assertTrue(report["research_only"])
        self.assertFalse(report["execution_authorized"])

    def test_1500_five_minute_bars_are_insufficient(self):
        with self.assertRaisesRegex(ValueError, "insufficient_4h_history"):
            report_from_five_minute(
                {"XRP/USDT:USDT": make_five(1500)},
                cutoff_ms=1500 * 300000,
            )


if __name__ == "__main__":
    unittest.main()
