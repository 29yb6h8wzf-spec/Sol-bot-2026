"""Read-only, deterministic dynamic-universe replay contract.

These fixtures are synthetic. Passing them is not historical market evidence.
"""
import unittest
from dataclasses import replace

from signals_v3.dynamic_universe import (
    UniverseObservation, UniverseThresholds, select_universe,
)


def observation(symbol, observed_at_ms=1000):
    return UniverseObservation(
        symbol=symbol, observed_at_ms=observed_at_ms,
        last_price_usd=10.0, quote_volume_24h_usd=20_000_000.0,
        spread_bps=2.0, bid_depth_10bps_usd=20_000.0,
        ask_depth_10bps_usd=20_000.0, min_notional_usd=5.0,
        status="TRADING", contract_type="PERPETUAL", quote_asset="USDT",
    )


class UniverseReadOnlyReplayTests(unittest.TestCase):
    def test_order_independent_selection_and_reason_map(self):
        observations = [observation("SOLUSDT"), observation("XRPUSDT"),
                        replace(observation("ETHUSDT"), spread_bps=50.0)]
        first = select_universe(observations, 1000)
        reverse = select_universe(reversed(observations), 1000)
        self.assertEqual(first, reverse)
        self.assertEqual(first[0], ("SOLUSDT", "XRPUSDT"))
        self.assertEqual(first[1]["ETHUSDT"], "spread_too_wide")

    def test_input_objects_unchanged_after_replay(self):
        observations = [observation("SOLUSDT")]
        snapshot = tuple(observations)
        limits = UniverseThresholds()
        select_universe(iter(observations), 1000, limits)
        self.assertEqual(tuple(observations), snapshot)
        self.assertEqual(limits, UniverseThresholds())

    def test_zero_min_notional_metadata_fails_closed(self):
        # A zero minimum notional is missing/invalid exchange metadata,
        # not evidence that every allocation can satisfy trading filters.
        invalid = replace(observation("SOLUSDT"), min_notional_usd=0.0)
        accepted, reasons = select_universe([invalid], 1000)
        self.assertEqual(accepted, ())
        self.assertEqual(reasons["SOLUSDT"], "invalid_market_data")

    def test_positive_min_notional_boundary_is_eligible(self):
        valid = replace(observation("SOLUSDT"), min_notional_usd=75.0)
        accepted, reasons = select_universe([valid], 1000)
        self.assertEqual(accepted, ("SOLUSDT",))
        self.assertEqual(reasons["SOLUSDT"], "eligible")

    def test_future_observation_never_eligible(self):
        accepted, reasons = select_universe(
            [observation("SOLUSDT", observed_at_ms=1001)], 1000)
        self.assertEqual(accepted, ())
        self.assertEqual(reasons["SOLUSDT"], "missing_point_in_time_evidence")

    def test_stale_observation_never_eligible(self):
        accepted, reasons = select_universe(
            [observation("SOLUSDT", observed_at_ms=1000)], 61001)
        self.assertEqual(accepted, ())
        self.assertEqual(reasons["SOLUSDT"], "missing_point_in_time_evidence")


if __name__ == "__main__":
    unittest.main()
