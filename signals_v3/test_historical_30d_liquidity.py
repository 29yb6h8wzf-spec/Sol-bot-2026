"""Offline tests for closed-day 30-day historical liquidity evidence."""
import unittest
from dataclasses import replace
from signals_v3.historical_30d_liquidity import (
    ClosedDailyVolume, DAY_MS, verify_30d_liquidity,
)


class Historical30dLiquidityTests(unittest.TestCase):
    def setUp(self):
        self.decision = 60 * DAY_MS + DAY_MS // 2
        self.rows = tuple(
            ClosedDailyVolume("SOLUSDT", (60 - i) * DAY_MS, 20_000_000.0)
            for i in range(1, 31)
        )

    def test_exact_threshold(self):
        result = verify_30d_liquidity(self.rows, "SOLUSDT", self.decision)
        self.assertTrue(result["meets_30d_liquidity_threshold"])
        self.assertFalse(result["provider_authenticity_verified"])

    def test_below_threshold(self):
        rows = tuple(replace(row, quote_volume_usd=19_999_999.0) for row in self.rows)
        self.assertFalse(verify_30d_liquidity(rows, "SOLUSDT", self.decision)["meets_30d_liquidity_threshold"])

    def test_missing_day_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "incomplete_30d_volume_evidence"):
            verify_30d_liquidity(self.rows[:-1], "SOLUSDT", self.decision)

    def test_duplicate_day_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate_daily_volume"):
            verify_30d_liquidity(self.rows[:-1] + (self.rows[0],), "SOLUSDT", self.decision)

    def test_oversized_bundle_rejected_before_iteration(self):
        with self.assertRaisesRegex(ValueError, "incomplete_30d_volume_evidence"):
            verify_30d_liquidity(self.rows + (self.rows[0],), "SOLUSDT", self.decision)

    def test_current_day_not_allowed(self):
        rows = self.rows[:-1] + (ClosedDailyVolume("SOLUSDT", 60 * DAY_MS, 20_000_000),)
        with self.assertRaisesRegex(ValueError, "non_point_in_time_daily_volume"):
            verify_30d_liquidity(rows, "SOLUSDT", self.decision)

    def test_future_day_not_allowed(self):
        rows = self.rows[:-1] + (ClosedDailyVolume("SOLUSDT", 61 * DAY_MS, 20_000_000),)
        with self.assertRaisesRegex(ValueError, "non_point_in_time_daily_volume"):
            verify_30d_liquidity(rows, "SOLUSDT", self.decision)

    def test_nonfinite_volume_rejected(self):
        rows = (replace(self.rows[0], quote_volume_usd=float("nan")),) + self.rows[1:]
        with self.assertRaisesRegex(ValueError, "invalid_daily_volume_value"):
            verify_30d_liquidity(rows, "SOLUSDT", self.decision)

    def test_bool_volume_rejected(self):
        rows = (replace(self.rows[0], quote_volume_usd=True),) + self.rows[1:]
        with self.assertRaisesRegex(ValueError, "invalid_daily_volume_value"):
            verify_30d_liquidity(rows, "SOLUSDT", self.decision)

    def test_mismatched_symbol_rejected(self):
        rows = (replace(self.rows[0], symbol="XRPUSDT"),) + self.rows[1:]
        with self.assertRaisesRegex(ValueError, "invalid_daily_volume_record"):
            verify_30d_liquidity(rows, "SOLUSDT", self.decision)

    def test_short_symbol_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid_volume_symbol"):
            verify_30d_liquidity(self.rows, "USDT", self.decision)

    def test_lowercase_symbol_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid_volume_symbol"):
            verify_30d_liquidity(self.rows, "solUSDT", self.decision)

    def test_pre_history_window_rejected(self):
        with self.assertRaisesRegex(ValueError, "insufficient_historical_calendar"):
            verify_30d_liquidity([], "SOLUSDT", 5 * DAY_MS)

    def test_first_complete_calendar_window(self):
        rows = tuple(
            ClosedDailyVolume("SOLUSDT", i * DAY_MS, 20_000_000)
            for i in range(30)
        )
        result = verify_30d_liquidity(rows, "SOLUSDT", 30 * DAY_MS)
        self.assertTrue(result["meets_30d_liquidity_threshold"])
        self.assertFalse(result["provider_authenticity_verified"])

    def test_decision_before_utc_midnight_cannot_use_current_day(self):
        decision = 60 * DAY_MS - 1
        with self.assertRaisesRegex(ValueError, "non_point_in_time_daily_volume"):
            verify_30d_liquidity(self.rows, "SOLUSDT", decision)

    def test_infinite_and_negative_volume_rejected(self):
        for bad in (float("inf"), float("-inf"), -1):
            with self.subTest(volume=bad):
                rows = (replace(self.rows[0], quote_volume_usd=bad),) + self.rows[1:]
                with self.assertRaisesRegex(ValueError, "invalid_daily_volume_value"):
                    verify_30d_liquidity(rows, "SOLUSDT", self.decision)

    def test_unordered_input_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid_daily_volume_records"):
            verify_30d_liquidity(set(self.rows), "SOLUSDT", self.decision)

    def test_noninteger_and_negative_decisions_rejected(self):
        for bad in (-1, 60.5 * DAY_MS, "5184000000", None):
            with self.subTest(decision=bad):
                with self.assertRaisesRegex(ValueError, "invalid_decision_timestamp"):
                    verify_30d_liquidity(self.rows, "SOLUSDT", bad)

    def test_extremely_large_integer_volume_rejected_without_overflow(self):
        rows = (replace(self.rows[0], quote_volume_usd=10 ** 1000),) + self.rows[1:]
        with self.assertRaisesRegex(ValueError, "invalid_daily_volume_value"):
            verify_30d_liquidity(rows, "SOLUSDT", self.decision)

    def test_finite_individual_volumes_with_infinite_sum_rejected(self):
        rows = tuple(replace(row, quote_volume_usd=1e308) for row in self.rows)
        with self.assertRaisesRegex(ValueError, "incomplete_30d_volume_evidence"):
            verify_30d_liquidity(rows, "SOLUSDT", self.decision)

    def test_sum_is_independent_of_valid_record_order(self):
        rows = tuple(
            replace(row, quote_volume_usd=(1e16 if i == 0 else 1.0))
            for i, row in enumerate(self.rows)
        )
        forward = verify_30d_liquidity(rows, "SOLUSDT", self.decision)
        backward = verify_30d_liquidity(tuple(reversed(rows)), "SOLUSDT", self.decision)
        self.assertEqual(
            forward["average_daily_quote_volume_usd"],
            backward["average_daily_quote_volume_usd"],
        )

    def test_boolean_decision_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid_decision_timestamp"):
            verify_30d_liquidity(self.rows, "SOLUSDT", True)


    def test_timestamp_boolean_and_fractional_day_rejected(self):
        for bad in (True, 59 * DAY_MS + 1, "5097600000", None):
            with self.subTest(timestamp=bad):
                rows = (replace(self.rows[0], day_start_ms=bad),) + self.rows[1:]
                with self.assertRaisesRegex(ValueError, "non_point_in_time_daily_volume"):
                    verify_30d_liquidity(rows, "SOLUSDT", self.decision)

    def test_wrong_record_type_rejected(self):
        rows = ({"symbol": "SOLUSDT", "day_start_ms": 59 * DAY_MS,
                 "quote_volume_usd": 20_000_000},) + self.rows[1:]
        with self.assertRaisesRegex(ValueError, "invalid_daily_volume_record"):
            verify_30d_liquidity(rows, "SOLUSDT", self.decision)

    def test_zero_volume_is_valid_but_below_threshold(self):
        rows = tuple(replace(row, quote_volume_usd=0) for row in self.rows)
        result = verify_30d_liquidity(rows, "SOLUSDT", self.decision)
        self.assertEqual(result["average_daily_quote_volume_usd"], 0)
        self.assertFalse(result["meets_30d_liquidity_threshold"])
        self.assertFalse(result["provider_authenticity_verified"])

if __name__ == "__main__":
    unittest.main()
