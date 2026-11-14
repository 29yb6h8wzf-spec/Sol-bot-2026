import unittest
from dataclasses import replace
from signals_v3.dynamic_universe import UniverseObservation,eligibility,select_universe

class DynamicUniverseTests(unittest.TestCase):
    def setUp(self):
        self.now=1_000_000
        self.obs=UniverseObservation("ADAUSDT",self.now,1.25,25_000_000,3.0,20_000,22_000,5.0,"TRADING","PERPETUAL","USDT")
    def test_eligible_new_symbol(self):
        self.assertEqual(eligibility(self.obs,self.now),(True,"eligible"))
    def test_price_boundaries(self):
        for p in (0.99,150.0):
            self.assertTrue(eligibility(replace(self.obs,last_price_usd=p),self.now)[0])
        for p in (0.989,150.01):
            self.assertFalse(eligibility(replace(self.obs,last_price_usd=p),self.now)[0])
    def test_no_future_data(self):
        self.assertEqual(eligibility(replace(self.obs,observed_at_ms=self.now+1),self.now)[1],"missing_point_in_time_evidence")
    def test_no_stale_data(self):
        self.assertFalse(eligibility(replace(self.obs,observed_at_ms=self.now-60_001),self.now)[0])
    def test_liquidity_and_market_checks(self):
        for kw in ({"spread_bps":11},{"bid_depth_10bps_usd":500},{"quote_volume_24h_usd":100},
                   {"min_notional_usd":100},{"status":"BREAK"},{"contract_type":"CURRENT_QUARTER"}):
            self.assertFalse(eligibility(replace(self.obs,**kw),self.now)[0])
    def test_select_dynamic_symbols(self):
        symbols,reasons=select_universe([self.obs,replace(self.obs,symbol="SOLUSDT",last_price_usd=200)],self.now)
        self.assertEqual(symbols,("ADAUSDT",))
        self.assertEqual(reasons["SOLUSDT"],"outside_price_range")
    def test_volume_gate_configuration_requires_real_boolean(self):
        low_volume=replace(self.obs,quote_volume_24h_usd=100)
        for invalid in (None,0,1,"false",[],{}):
            with self.subTest(invalid=invalid):
                self.assertEqual(
                    eligibility(low_volume,self.now,enforce_24h_volume=invalid),
                    (False,"invalid_volume_gate_configuration"))
                with self.assertRaisesRegex(ValueError,"invalid_volume_gate_configuration"):
                    select_universe([low_volume],self.now,enforce_24h_volume=invalid)
                with self.assertRaisesRegex(ValueError,"invalid_volume_gate_configuration"):
                    select_universe([],self.now,enforce_24h_volume=invalid)
        self.assertEqual(eligibility(low_volume,self.now,enforce_24h_volume=False),(True,"eligible"))
        self.assertEqual(eligibility(low_volume,self.now,enforce_24h_volume=True)[1],"insufficient_volume")
if __name__=="__main__":unittest.main()
