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

    def test_boolean_decision_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid_decision_timestamp"):
            verify_30d_liquidity(self.rows, "SOLUSDT", True)


if __name__ == "__main__":
    unittest.main()
