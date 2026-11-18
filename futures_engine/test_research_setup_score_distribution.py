"""Tests for offline-only SOL/XRP setup score distribution."""
import unittest

from futures_engine.research_setup_score_distribution import score_band, summarize_setups


class ScoreDistributionTests(unittest.TestCase):
    def test_score_boundaries_and_invalid_types(self):
        for score, expected in ((0, "below_70"), (69, "below_70"),
                                (70, "70_79"), (79, "70_79"),
                                (80, "80_84"), (84, "80_84"),
                                (85, "85_plus"), (100, "85_plus"),
                                (-1, "invalid_score"), (101, "invalid_score"),
                                (85.0, "invalid_score"), (True, "invalid_score"),
                                (None, "invalid_score")):
            with self.subTest(score=score):
                self.assertEqual(score_band(score), expected)

    def test_counts_no_setup_and_strategy_direction(self):
        scans = [
            {"symbol": "SOL/USDT:USDT", "setups": []},
            {"symbol": "SOL/USDT:USDT", "setups": [
                {"strategy": "RSI_BOLL", "direction": "LONG", "score": 80},
                {"strategy": "MACD_VOLUME", "direction": "SHORT", "score": 85}]},
            {"symbol": "XRP/USDT:USDT", "setups": [
                {"strategy": "EMA_ADX", "direction": "LONG", "score": 79},
                {"strategy": "EMA_ADX", "direction": "LONG", "score": None}]},
        ]
        result = summarize_setups(scans)
        self.assertEqual(result["totals"]["scans"], 3)
        self.assertEqual(result["totals"]["no_setup_scans"], 1)
        self.assertEqual(result["totals"]["setups"], 4)
        self.assertEqual(result["totals"]["80_84"], 1)
        self.assertEqual(result["totals"]["85_plus"], 1)
        self.assertEqual(result["totals"]["70_79"], 1)
        self.assertEqual(result["totals"]["invalid_score"], 1)
        self.assertFalse(result["execution_authorized"])
        self.assertEqual(len(result["by_symbol_strategy_direction"]), 3)

    def test_fail_closed_for_invalid_scan_data(self):
        for scans in ([{"symbol": "BTC/USDT:USDT", "setups": []}],
                      [{"symbol": "SOL/USDT:USDT"}],
                      [{"symbol": "SOL/USDT:USDT", "setups": [{"strategy": "X", "direction": "BUY", "score": 90}]}],
                      [None]):
            with self.subTest(scans=scans):
                with self.assertRaises(ValueError):
                    summarize_setups(scans)


if __name__ == "__main__":
    unittest.main()
