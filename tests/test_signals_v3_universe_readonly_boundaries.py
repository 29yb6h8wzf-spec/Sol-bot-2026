"""Read-only boundary tests for dynamic universe point-in-time decisions.

Synthetic fixtures only; these do not establish historical market coverage.
"""
import unittest

from signals_v3.dynamic_universe import (
    UniverseObservation, UniverseThresholds, eligibility, select_universe,
)


def observation(**overrides):
    fields = dict(
        symbol="SOLUSDT", observed_at_ms=1000, last_price_usd=100.0,
        quote_volume_24h_usd=20_000_000.0, spread_bps=2.0,
        bid_depth_10bps_usd=20_000.0, ask_depth_10bps_usd=20_000.0,
        min_notional_usd=5.0, status="TRADING",
        contract_type="PERPETUAL", quote_asset="USDT",
    )
    fields.update(overrides)
    return UniverseObservation(**fields)


class ReadOnlyUniverseBoundaryTests(unittest.TestCase):
    def test_future_observation_is_not_visible(self):
        ok, reason = eligibility(observation(observed_at_ms=1001), 1000)
        self.assertFalse(ok)
        self.assertEqual(reason, "missing_point_in_time_evidence")

    def test_age_boundary_inclusive_then_expires(self):
        limits = UniverseThresholds(max_observation_age_ms=60)
        self.assertEqual(eligibility(observation(), 1060, limits), (True, "eligible"))
        self.assertEqual(
            eligibility(observation(), 1061, limits),
            (False, "missing_point_in_time_evidence"),
        )

    def test_price_range_boundaries(self):
        self.assertTrue(eligibility(observation(last_price_usd=0.99), 1000)[0])
        self.assertTrue(eligibility(observation(last_price_usd=150.0), 1000)[0])
        self.assertEqual(
            eligibility(observation(last_price_usd=150.01), 1000)[1],
            "outside_price_range",
        )

    def test_no_stale_symbol_can_enter_batch(self):
        accepted, reasons = select_universe([
            observation(symbol="SOLUSDT"),
            observation(symbol="XRPUSDT", observed_at_ms=1),
        ], 1000, UniverseThresholds(max_observation_age_ms=60))
        self.assertEqual(accepted, ("SOLUSDT",))
        self.assertEqual(reasons["XRPUSDT"], "missing_point_in_time_evidence")

    def test_duplicate_symbol_is_rejected_not_overwritten(self):
        with self.assertRaisesRegex(ValueError, "duplicate_universe_observation"):
            select_universe([observation(), observation(last_price_usd=1.0)], 1000)

    def test_invalid_empty_scan_configuration_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid_universe_thresholds"):
            select_universe([], 1000, UniverseThresholds(max_spread_bps=float("nan")))


if __name__ == "__main__":
    unittest.main()
