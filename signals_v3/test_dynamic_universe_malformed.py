"""Malformed historical universe provider payloads must never pass eligibility."""
import unittest
from dataclasses import replace
from signals_v3.dynamic_universe import UniverseObservation, eligibility, select_universe

class MalformedUniverseTests(unittest.TestCase):
    def setUp(self):
        self.obs=UniverseObservation("SOLUSDT",1000,100.0,20_000_000.0,2.0,
            20_000.0,20_000.0,5.0,"TRADING","PERPETUAL","USDT")
    def test_valid_observation(self):
        self.assertEqual(eligibility(self.obs,1000),(True,"eligible"))
    def test_non_numeric_fields_fail_closed(self):
        for field,value in (("last_price_usd","100"),("spread_bps",None),
                            ("bid_depth_10bps_usd",[]),("min_notional_usd",True),
                            ("quote_volume_24h_usd",{})):
            with self.subTest(field=field):
                self.assertEqual(eligibility(replace(self.obs,**{field:value}),1000),
                                 (False,"invalid_market_data"))
    def test_bad_timestamps_fail_closed(self):
        for observed,decision in ((True,1000),("1000",1000),(1000,True),(-1,1000),(1000,-1)):
            with self.subTest(observed=observed,decision=decision):
                self.assertEqual(eligibility(replace(self.obs,observed_at_ms=observed),decision),
                                 (False,"invalid_market_data"))
    def test_duplicate_snapshot_symbols_rejected(self):
        with self.assertRaisesRegex(ValueError,"duplicate_universe_observation"):
            select_universe((self.obs,self.obs),1000)
    def test_malformed_snapshot_identity_rejected(self):
        with self.assertRaisesRegex(ValueError,"invalid_universe_observation_identity"):
            select_universe((replace(self.obs,symbol=None),),1000)
    def test_invalid_identity_fail_closed(self):
        self.assertEqual(eligibility(replace(self.obs,symbol=None),1000),
                         (False,"invalid_market_data"))
        self.assertEqual(eligibility(None,1000),(False,"invalid_market_data"))

if __name__=="__main__":
    unittest.main()
