"""Offline contract tests for malformed dynamic-universe batches."""
import unittest

from dataclasses import replace
from signals_v3.dynamic_universe import select_universe, eligibility, UniverseThresholds, UniverseObservation


class DynamicUniverseBatchContractTests(unittest.TestCase):
    def test_non_iterable_batches_fail_closed(self):
        for value in (0, 1.5, False, object()):
            with self.subTest(value=repr(value)):
                with self.assertRaisesRegex(ValueError, "invalid_universe_observations"):
                    select_universe(value, 1000)

    def test_empty_valid_iterable_is_not_a_market_evidence_claim(self):
        for value in ([], (), iter(())):
            with self.subTest(kind=type(value).__name__):
                selected, reasons = select_universe(value, 1000)
                self.assertEqual(selected, ())
                self.assertEqual(reasons, {})

    def test_invalid_config_rejected_before_iterating_empty_batch(self):
        limits = UniverseThresholds(max_observation_age_ms=-1)
        with self.assertRaisesRegex(ValueError, "invalid_universe_thresholds"):
            select_universe(iter(()), 1000, limits)


    def test_oversized_integer_threshold_rejected_without_overflow(self):
        limits = UniverseThresholds(min_quote_volume_24h_usd=10**1000)
        with self.assertRaisesRegex(ValueError, "invalid_universe_thresholds"):
            select_universe([], 1000, limits)

    def test_oversized_provider_number_fails_closed_without_overflow(self):
        observation = UniverseObservation(
            symbol="SOLUSDT", observed_at_ms=1000, last_price_usd=100.0,
            quote_volume_24h_usd=20_000_000.0, spread_bps=2.0,
            bid_depth_10bps_usd=20_000.0, ask_depth_10bps_usd=20_000.0,
            min_notional_usd=5.0, status="TRADING",
            contract_type="PERPETUAL", quote_asset="USDT")
        for field in ("last_price_usd", "quote_volume_24h_usd",
                      "spread_bps", "bid_depth_10bps_usd",
                      "ask_depth_10bps_usd", "min_notional_usd"):
            with self.subTest(field=field):
                malformed = replace(observation, **{field: 10**1000})
                self.assertEqual(eligibility(malformed, 1000),
                                 (False, "invalid_market_data"))
                self.assertEqual(select_universe([malformed], 1000)[0], ())


if __name__ == "__main__":
    unittest.main()
