"""Tests for conservative outcome classification and causal entry."""
import unittest
from futures_engine.research_score85_outcomes import evaluate_one


def rows(high=100.5, low=99.5, close=100):
    return [[i * 300000, 100.0, high, low, close, 10.0] for i in range(52)]


class OutcomeTests(unittest.TestCase):
    def test_no_entry_on_signal_candle(self):
        data = rows()
        data[0] = [0, 100.0, 110.0, 90.0, 100.0, 10.0]
        result = evaluate_one(data, 0, "LONG")
        self.assertEqual(result["reason"], "time")
        self.assertEqual(result["entry_open_ms"], 300000)

    def test_same_bar_target_and_stop_counts_as_stop(self):
        data = rows(high=103, low=98)
        result = evaluate_one(data, 0, "LONG")
        self.assertEqual(result["reason"], "stop_or_ambiguous")
        self.assertAlmostEqual(result["net_pct"], -1.14)

    def test_short_target_after_entry(self):
        data = rows(high=100.5, low=97.0)
        result = evaluate_one(data, 0, "SHORT")
        self.assertEqual(result["reason"], "target")
        self.assertAlmostEqual(result["net_pct"], 1.86)

    def test_insufficient_future_is_excluded(self):
        self.assertIsNone(evaluate_one(rows()[:10], 0, "LONG"))


if __name__ == "__main__":
    unittest.main()
