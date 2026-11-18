"""Offline JSON gap reporting tests."""
import json
import unittest

from signals_v3.historical_market_coverage_report import audit_historical_market_coverage
from signals_v3.historical_coverage_gaps import (
    historical_coverage_report_json, summarize_historical_coverage,
)


def funding(t):
    return {"symbol": "SOLUSDT", "funding_time_ms": t, "funding_rate": "0.0001"}


def book(t):
    return {"symbol": "SOLUSDT", "timestamp_ms": t, "spread_bps": "2",
            "bid_depth_10bps_usd": "1000", "ask_depth_10bps_usd": "1000"}


class GapReportingTests(unittest.TestCase):
    def report(self, funds, books):
        return audit_historical_market_coverage(
            funds, [1000, 2000], books, [1000, 2000],
            "SOLUSDT", 100,
        )

    def test_missing_and_stale_times_are_reported(self):
        summary = summarize_historical_coverage(
            self.report([funding(1000)], [book(1000)])
        )
        self.assertEqual(summary["gap_timestamps_ms"]["funding_missing"], [2000])
        self.assertEqual(summary["gap_timestamps_ms"]["orderbook_stale"], [2000])
        self.assertFalse(summary["integrity_coverage_complete"])

    def test_duplicate_funding_is_counted(self):
        summary = summarize_historical_coverage(
            self.report([funding(1000), funding(1000), funding(2000)],
                        [book(1000), book(2000)])
        )
        self.assertEqual(summary["gap_counts"]["funding_duplicate"], 1)

    def test_complete_integrity_does_not_claim_authenticity(self):
        summary = summarize_historical_coverage(
            self.report([funding(1000), funding(2000)],
                        [book(1000), book(2000)])
        )
        self.assertTrue(summary["integrity_coverage_complete"])
        self.assertFalse(summary["historical_evidence_verified"])
        self.assertFalse(summary["funding_history_verified"])
        self.assertFalse(summary["orderbook_history_verified"])

    def test_json_is_deterministic(self):
        report = self.report([funding(1000)], [book(1000)])
        self.assertEqual(historical_coverage_report_json(report),
                         historical_coverage_report_json(report))
        self.assertEqual(json.loads(historical_coverage_report_json(report))["schema_version"], 1)

    def test_invalid_report_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "invalid_historical_coverage_report"):
            summarize_historical_coverage({})


if __name__ == "__main__":
    unittest.main()
