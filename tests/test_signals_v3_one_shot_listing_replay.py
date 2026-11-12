"""Offline regression for one-shot historical market listings.

No exchange calls or orders; these are synthetic snapshots, not historical evidence.
"""
import unittest

from signals_v3.dynamic_universe import UniverseObservation
from signals_v3.historical_universe_replay import replay_complete_universe


def observation(symbol, timestamp):
    return UniverseObservation(
        symbol=symbol, observed_at_ms=timestamp, last_price_usd=10.0,
        quote_volume_24h_usd=20_000_000.0, spread_bps=2.0,
        bid_depth_10bps_usd=20_000.0, ask_depth_10bps_usd=20_000.0,
        min_notional_usd=5.0, status="TRADING",
        contract_type="PERPETUAL", quote_asset="USDT")


class OneShotListingReplayTests(unittest.TestCase):
    def test_generator_listing_matches_tuple_listing(self):
        decisions = [
            {"decision_ms": 1000, "expected_symbols": (s for s in ("SOLUSDT",)),
             "observations": (observation("SOLUSDT", 1000),)},
            {"decision_ms": 2000, "expected_symbols": (s for s in ("SOLUSDT", "XRPUSDT")),
             "observations": (observation("SOLUSDT", 2000), observation("XRPUSDT", 2000))},
        ]
        result = replay_complete_universe(decisions, (1000, 2000))
        self.assertEqual(result[0]["eligible_symbols"], ("SOLUSDT",))
        self.assertEqual(result[1]["listed_added"], ("XRPUSDT",))
        self.assertEqual(result[1]["listed_removed"], ())

    def test_non_iterable_listing_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "invalid_historical_market_listing"):
            replay_complete_universe((
                {"decision_ms": 1000, "expected_symbols": 42,
                 "observations": (observation("SOLUSDT", 1000),)},
            ), (1000,))

    def test_generator_duplicate_listing_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid_historical_market_listing"):
            replay_complete_universe((
                {"decision_ms": 1000, "expected_symbols": (s for s in ("SOLUSDT", "SOLUSDT")),
                 "observations": (observation("SOLUSDT", 1000),)},
            ), (1000,))


if __name__ == "__main__":
    unittest.main()
