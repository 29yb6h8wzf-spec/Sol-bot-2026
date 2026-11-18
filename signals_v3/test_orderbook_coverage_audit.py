"""No-lookahead order-book coverage regression tests."""
import unittest
from signals_v3.orderbook_coverage_audit import audit_orderbook_coverage


def sample(timestamp, **overrides):
    item = {"symbol": "SOLUSDT", "timestamp_ms": timestamp,
            "spread_bps": "2.0", "bid_depth_10bps_usd": "10000",
            "ask_depth_10bps_usd": "10000"}
    item.update(overrides)
    return item


class OrderbookCoverageAuditTests(unittest.TestCase):
    def test_exact_timestamp_is_integrity_only(self):
        result = audit_orderbook_coverage([sample(1000)], [1000], "SOLUSDT", 0)
        self.assertTrue(result["orderbook_coverage_complete"])
        self.assertFalse(result["orderbook_history_verified"])

    def test_prior_sample_within_age(self):
        result = audit_orderbook_coverage([sample(990)], [1000], "SOLUSDT", 10)
        self.assertEqual(result["matched_decision_samples"], ((1000, 990),))

    def test_future_sample_not_used(self):
        result = audit_orderbook_coverage([sample(1001)], [1000], "SOLUSDT", 100)
        self.assertEqual(result["missing_decisions"], (1000,))
        self.assertFalse(result["orderbook_coverage_complete"])

    def test_stale_sample_rejected(self):
        result = audit_orderbook_coverage([sample(980)], [1000], "SOLUSDT", 10)
        self.assertEqual(result["stale_decisions"], (1000,))

    def test_duplicate_timestamp_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate_orderbook_timestamp"):
            audit_orderbook_coverage([sample(1000), sample(1000)], [1000], "SOLUSDT", 0)

    def test_invalid_depth_rejected(self):
        for bad in ("NaN", "-1", "Infinity"):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ValueError, "invalid_orderbook_sample"):
                    audit_orderbook_coverage([sample(1000, bid_depth_10bps_usd=bad)],
                                             [1000], "SOLUSDT", 0)

    def test_lazy_schedule_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid_orderbook_schedule"):
            audit_orderbook_coverage([], iter([1000]), "SOLUSDT", 0)

    def test_boolean_age_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid_orderbook_max_age"):
            audit_orderbook_coverage([sample(1000)], [1000], "SOLUSDT", True)

    def test_latest_past_sample_selected(self):
        result = audit_orderbook_coverage([sample(900), sample(995), sample(1001)],
                                          [1000], "SOLUSDT", 10)
        self.assertEqual(result["matched_decision_samples"], ((1000, 995),))


if __name__ == "__main__":
    unittest.main()
