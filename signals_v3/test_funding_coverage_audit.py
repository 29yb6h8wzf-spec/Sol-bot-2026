"""Offline negative controls for funding event coverage."""
import unittest

from signals_v3.funding_coverage_audit import audit_funding_coverage


def event(timestamp, rate="0.0001"):
    return {"symbol": "SOLUSDT", "funding_time_ms": timestamp, "funding_rate": rate}


class FundingCoverageAuditTests(unittest.TestCase):
    def test_complete_schedule_is_integrity_only(self):
        result = audit_funding_coverage([event(1000), event(2000)], [1000, 2000], "SOLUSDT")
        self.assertTrue(result["funding_coverage_complete"])
        self.assertFalse(result["funding_history_verified"])
        self.assertFalse(result["provider_authenticity_verified"])

    def test_missing_event_fails_coverage(self):
        result = audit_funding_coverage([event(1000)], [1000, 2000], "SOLUSDT")
        self.assertFalse(result["funding_coverage_complete"])
        self.assertEqual(result["missing_event_times"], (2000,))

    def test_duplicate_event_fails_coverage(self):
        result = audit_funding_coverage([event(1000), event(1000)], [1000], "SOLUSDT")
        self.assertFalse(result["funding_coverage_complete"])
        self.assertEqual(result["duplicate_event_times"], (1000,))

    def test_unexpected_event_fails_coverage(self):
        result = audit_funding_coverage([event(1000), event(3000)], [1000, 2000], "SOLUSDT")
        self.assertFalse(result["funding_coverage_complete"])
        self.assertEqual(result["unexpected_event_times"], (3000,))

    def test_nonfinite_rate_rejected(self):
        for rate in ("NaN", "Infinity", "bad"):
            with self.subTest(rate=rate):
                with self.assertRaisesRegex(ValueError, "invalid_funding_record"):
                    audit_funding_coverage([event(1000, rate)], [1000], "SOLUSDT")

    def test_lazy_schedule_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid_funding_schedule"):
            audit_funding_coverage([], iter([1000]), "SOLUSDT")

    def test_boolean_timestamp_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid_funding_record"):
            audit_funding_coverage([event(True)], [1000], "SOLUSDT")

    def test_wrong_symbol_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid_funding_record"):
            audit_funding_coverage([{"symbol": "XRPUSDT", "funding_time_ms": 1000, "funding_rate": "0.1"}], [1000], "SOLUSDT")


if __name__ == "__main__":
    unittest.main()
