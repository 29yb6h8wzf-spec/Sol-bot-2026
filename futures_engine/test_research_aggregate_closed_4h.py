"""Tests for strictly closed 4h aggregation of 5m market data."""
import unittest

from futures_engine.research_aggregate_closed_4h import aggregate_closed_four_hour


def rows(n, start=0):
    return [[start + i * 300000, 100, 102 + (i % 3), 99, 101, 2]
            for i in range(n)]


class ClosedFourHourAggregationTests(unittest.TestCase):
    def test_complete_bucket_aggregates_ohlcv(self):
        result = aggregate_closed_four_hour(rows(48))
        self.assertEqual(result, [[0, 100, 104, 99, 101, 96]])

    def test_partial_last_bucket_not_emitted(self):
        result = aggregate_closed_four_hour(rows(49))
        self.assertEqual(len(result), 1)

    def test_partial_first_bucket_not_emitted(self):
        result = aggregate_closed_four_hour(rows(95, start=300000))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], 14400000)

    def test_gap_fails_closed(self):
        data = rows(48)
        data[5][0] += 300000
        with self.assertRaises(ValueError):
            aggregate_closed_four_hour(data)

    def test_non_utc_aligned_bars_rejected(self):
        data = rows(48)
        data[0][0] += 1
        with self.assertRaises(ValueError):
            aggregate_closed_four_hour(data)


if __name__ == "__main__":
    unittest.main()
