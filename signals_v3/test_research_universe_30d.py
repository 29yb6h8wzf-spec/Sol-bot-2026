"""Offline regression tests for research-only 30d universe gate."""
import unittest
from signals_v3.dynamic_universe import (
    UniverseObservation, select_research_universe_30d,
)
from signals_v3.historical_30d_liquidity import ClosedDailyVolume, DAY_MS


class ResearchUniverse30dTests(unittest.TestCase):
    def setUp(self):
        self.decision = 60 * DAY_MS + 1000
        self.obs = UniverseObservation(
            symbol="SOLUSDT", observed_at_ms=self.decision - 1000,
            last_price_usd=100.0, quote_volume_24h_usd=25_000_000.0,
            spread_bps=2.0, bid_depth_10bps_usd=20_000.0,
            ask_depth_10bps_usd=20_000.0, min_notional_usd=5.0,
            status="TRADING", contract_type="PERPETUAL", quote_asset="USDT",
        )
        self.rows = tuple(
            ClosedDailyVolume("SOLUSDT", (60 - i) * DAY_MS, 25_000_000.0)
            for i in range(1, 31)
        )

    def test_legacy_24h_volume_does_not_override_30d_research_gate(self):
        from dataclasses import replace
        from signals_v3.dynamic_universe import select_universe
        low_24h = replace(self.obs, quote_volume_24h_usd=5_000_000.0)
        legacy, legacy_reasons = select_universe([low_24h], self.decision)
        self.assertEqual(legacy, ())
        self.assertEqual(legacy_reasons["SOLUSDT"], "insufficient_volume")
        research, research_reasons = select_research_universe_30d(
            [low_24h], {"SOLUSDT": self.rows}, self.decision
        )
        self.assertEqual(research, ())
        self.assertEqual(research_reasons["SOLUSDT"], "unverified_30d_volume_provenance")

    def test_missing_history_fails_closed(self):
        accepted, reasons = select_research_universe_30d([self.obs], {}, self.decision)
        self.assertEqual(accepted, ())
        self.assertEqual(reasons["SOLUSDT"], "missing_30d_volume_evidence")

    def test_valid_arithmetic_not_authenticity(self):
        accepted, reasons = select_research_universe_30d(
            [self.obs], {"SOLUSDT": self.rows}, self.decision
        )
        self.assertEqual(accepted, ())
        self.assertEqual(reasons["SOLUSDT"], "unverified_30d_volume_provenance")

    def test_incomplete_history_fails_closed(self):
        accepted, reasons = select_research_universe_30d(
            [self.obs], {"SOLUSDT": self.rows[:-1]}, self.decision
        )
        self.assertEqual(accepted, ())
        self.assertEqual(reasons["SOLUSDT"], "invalid_30d_volume_evidence")

    def test_invalid_mapping_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid_historical_volume_mapping"):
            select_research_universe_30d([self.obs], None, self.decision)

    def test_no_current_day_data(self):
        bad = self.rows[:-1] + (ClosedDailyVolume("SOLUSDT", 60 * DAY_MS, 25_000_000.0),)
        accepted, reasons = select_research_universe_30d(
            [self.obs], {"SOLUSDT": bad}, self.decision
        )
        self.assertEqual(accepted, ())
        self.assertEqual(reasons["SOLUSDT"], "invalid_30d_volume_evidence")


if __name__ == "__main__":
    unittest.main()
