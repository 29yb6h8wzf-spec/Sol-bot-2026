"""Combined coverage contract tests, with no exchange credentials."""
import unittest

from signals_v3.historical_market_coverage_report import audit_historical_market_coverage


def funding(t):
    return {"symbol": "SOLUSDT", "funding_time_ms": t, "funding_rate": "0.0001"}


def depth(t):
    return {"symbol": "SOLUSDT", "timestamp_ms": t, "spread_bps": "1",
            "bid_depth_10bps_usd": "1000", "ask_depth_10bps_usd": "1000"}


def audit(funding_records=None, depth_samples=None):
    return audit_historical_market_coverage(
        [funding(1000)] if funding_records is None else funding_records,
        [1000],
        [depth(1000)] if depth_samples is None else depth_samples,
        [1000], "SOLUSDT", 0,
    )


class CombinedCoverageTests(unittest.TestCase):
    def test_complete_integrity_does_not_verify_history(self):
        result = audit()
        self.assertTrue(result["combined_integrity_coverage_complete"])
        self.assertFalse(result["historical_evidence_verified"])
        self.assertFalse(result["provider_authenticity_verified"])
        self.assertFalse(result["funding_history_verified"])
        self.assertFalse(result["orderbook_history_verified"])

    def test_missing_funding_blocks_combined_coverage(self):
        result = audit(funding_records=[])
        self.assertFalse(result["combined_integrity_coverage_complete"])
        self.assertEqual(result["funding"]["missing_event_times"], (1000,))

    def test_missing_orderbook_blocks_combined_coverage(self):
        result = audit(depth_samples=[])
        self.assertFalse(result["combined_integrity_coverage_complete"])
        self.assertEqual(result["orderbook"]["missing_decisions"], (1000,))

    def test_future_orderbook_blocks_combined_coverage(self):
        result = audit(depth_samples=[depth(1001)])
        self.assertFalse(result["combined_integrity_coverage_complete"])
        self.assertEqual(result["orderbook"]["missing_decisions"], (1000,))

    def test_duplicate_funding_blocks_combined_coverage(self):
        result = audit(funding_records=[funding(1000), funding(1000)])
        self.assertFalse(result["combined_integrity_coverage_complete"])
        self.assertEqual(result["funding"]["duplicate_event_times"], (1000,))


if __name__ == "__main__":
    unittest.main()
