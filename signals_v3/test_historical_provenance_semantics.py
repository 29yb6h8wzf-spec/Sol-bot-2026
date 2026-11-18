"""Research-only regression: complete listings are not authenticated history."""
import unittest

from signals_v3.dynamic_universe import UniverseObservation
from signals_v3.historical_universe_gate import verify_decision_snapshot
from signals_v3.historical_universe_replay import replay_complete_universe


class HistoricalProvenanceSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.observation = UniverseObservation(
            symbol="SOLUSDT", observed_at_ms=1500,
            last_price_usd=100.0, quote_volume_24h_usd=20_000_000.0,
            spread_bps=2.0, bid_depth_10bps_usd=20_000.0,
            ask_depth_10bps_usd=20_000.0, min_notional_usd=5.0,
            status="TRADING", contract_type="PERPETUAL", quote_asset="USDT")

    def test_matching_symbols_do_not_verify_provenance(self):
        result = verify_decision_snapshot([self.observation], 1500, ["SOLUSDT"])
        self.assertTrue(result["historical_universe_complete"])
        self.assertIs(result["historical_provenance_verified"], False)

    def test_replay_does_not_upgrade_provenance(self):
        decisions = [{
            "decision_ms": 1500,
            "expected_symbols": ["SOLUSDT"],
            "observations": [self.observation],
        }]
        result = replay_complete_universe(decisions, [1500])
        self.assertEqual(len(result), 1)
        self.assertIs(result[0]["historical_provenance_verified"], False)

    def test_incomplete_listing_still_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "incomplete_historical_universe"):
            verify_decision_snapshot([self.observation], 1500, ["XRPUSDT"])


if __name__ == "__main__":
    unittest.main()
