"""Read-only dynamic-universe boundary and point-in-time regression tests.

Synthetic observations are NOT historical market evidence.
"""
import unittest
from dataclasses import replace

from signals_v3.dynamic_universe import (
    UniverseObservation, UniverseThresholds, eligibility, select_universe,
)


def observation(**changes):
    base = UniverseObservation(
        symbol="SOLUSDT", observed_at_ms=1000, last_price_usd=0.99,
        quote_volume_24h_usd=10_000_000.0, spread_bps=10.0,
        bid_depth_10bps_usd=10_000.0, ask_depth_10bps_usd=10_000.0,
        min_notional_usd=75.0, status="TRADING",
        contract_type="PERPETUAL", quote_asset="USDT",
    )
    return replace(base, **changes)


class PointInTimeUniverseBoundaryTests(unittest.TestCase):
    def test_exact_thresholds_are_inclusive(self):
        self.assertEqual(eligibility(observation(), 61_000), (True, "eligible"))
        self.assertEqual(
            eligibility(observation(last_price_usd=150.0), 61_000),
            (True, "eligible"),
        )

    def test_stale_and_future_observations_never_enter_universe(self):
        for decision, reason in (
            (999, "missing_point_in_time_evidence"),
            (61_001, "missing_point_in_time_evidence"),
        ):
            with self.subTest(decision=decision):
                self.assertEqual(eligibility(observation(), decision), (False, reason))
                self.assertEqual(select_universe([observation()], decision)[0], ())

    def test_each_liquidity_or_sizing_gate_rejects(self):
        cases = (
            ({"quote_volume_24h_usd": 9_999_999.0}, "insufficient_volume"),
            ({"spread_bps": 10.01}, "spread_too_wide"),
            ({"bid_depth_10bps_usd": 9_999.0}, "insufficient_depth"),
            ({"ask_depth_10bps_usd": 9_999.0}, "insufficient_depth"),
            ({"min_notional_usd": 75.01}, "min_notional_exceeds_allocation"),
            ({"last_price_usd": 0.989}, "outside_price_range"),
            ({"last_price_usd": 150.001}, "outside_price_range"),
        )
        for changes, reason in cases:
            with self.subTest(changes=changes):
                self.assertEqual(eligibility(observation(**changes), 1000), (False, reason))

    def test_batch_never_uses_future_observation_to_rescue_stale_one(self):
        old = observation(symbol="SOLUSDT", observed_at_ms=1000)
        future = observation(symbol="XRPUSDT", observed_at_ms=62_000)
        selected, reasons = select_universe((x for x in (old, future)), 61_001)
        self.assertEqual(selected, ())
        self.assertEqual(reasons, {
            "SOLUSDT": "missing_point_in_time_evidence",
            "XRPUSDT": "missing_point_in_time_evidence",
        })

    def test_invalid_configuration_fails_even_when_batch_empty(self):
        for limits in (
            UniverseThresholds(max_spread_bps=float("inf")),
            UniverseThresholds(available_notional_usd=-1),
            UniverseThresholds(max_observation_age_ms=True),
        ):
            with self.subTest(limits=limits):
                with self.assertRaisesRegex(ValueError, "invalid_universe_thresholds"):
                    select_universe([], 1000, limits)


if __name__ == "__main__":
    unittest.main()
