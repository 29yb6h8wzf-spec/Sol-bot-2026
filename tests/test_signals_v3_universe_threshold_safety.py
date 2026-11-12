"""Fail-closed configuration regression; no network or order endpoints."""
import unittest
from dataclasses import replace
from signals_v3.dynamic_universe import UniverseObservation, UniverseThresholds, eligibility, select_universe

OBS=UniverseObservation(symbol="SOLUSDT",observed_at_ms=1000,last_price_usd=100,
    quote_volume_24h_usd=20_000_000,spread_bps=2,bid_depth_10bps_usd=20_000,
    ask_depth_10bps_usd=20_000,min_notional_usd=5,status="TRADING",
    contract_type="PERPETUAL",quote_asset="USDT")

class ThresholdSafety(unittest.TestCase):
    def test_default_is_eligible(self):
        self.assertEqual(eligibility(OBS,1000),(True,"eligible"))

    def test_nonfinite_or_negative_limits_fail_closed(self):
        for field,value in (("max_spread_bps",float("nan")),
            ("min_quote_volume_24h_usd",float("inf")),
            ("min_each_side_depth_10bps_usd",-1),
            ("available_notional_usd",float("-inf")),
            ("max_observation_age_ms",-1),
            ("max_observation_age_ms",True)):
            with self.subTest(field=field,value=value):
                limits=replace(UniverseThresholds(),**{field:value})
                self.assertEqual(eligibility(OBS,1000,limits),(False,"invalid_universe_thresholds"))
                with self.assertRaisesRegex(ValueError, "^invalid_universe_thresholds$"):
                    select_universe([OBS],1000,limits)
                with self.assertRaisesRegex(ValueError, "^invalid_universe_thresholds$"):
                    select_universe([],1000,limits)

    def test_wrong_configuration_type(self):
        self.assertEqual(eligibility(OBS,1000,{}),(False,"invalid_universe_thresholds"))

if __name__=="__main__":
    unittest.main()
