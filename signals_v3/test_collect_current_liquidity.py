import unittest
from signals_v3.collect_current_liquidity import snapshot_symbol

class CurrentLiquidityCollectorTests(unittest.TestCase):
    def test_public_snapshot(self):
        calls=[]
        def fetch(path,params=None):
            calls.append(path)
            if path.endswith("exchangeInfo"):
                return {"symbols":[{"symbol":"SOLUSDT","status":"TRADING","contractType":"PERPETUAL","quoteAsset":"USDT","filters":[{"filterType":"MIN_NOTIONAL","notional":"5"}]}]}
            if path.endswith("24hr"):
                return {"lastPrice":"100","quoteVolume":"25000000"}
            return {"bids":[["99.99","200"]],"asks":[["100.01","200"]]}
        result=snapshot_symbol("SOLUSDT",fetch=fetch,clock_ms=lambda:100000)
        self.assertEqual(result["min_notional_usd"],5)
        self.assertGreater(result["bid_depth_10bps_usd"],19000)
        self.assertTrue(result["current_only"])
        self.assertFalse(result["historical_universe_verified"])
        self.assertEqual(len(calls),3)
    def test_empty_book_fails_closed(self):
        def fetch(path,params=None):
            if path.endswith("exchangeInfo"):
                return {"symbols":[{"symbol":"SOLUSDT","status":"TRADING","contractType":"PERPETUAL","quoteAsset":"USDT","filters":[{"filterType":"MIN_NOTIONAL","notional":"5"}]}]}
            if path.endswith("24hr"):
                return {"lastPrice":"100","quoteVolume":"25000000"}
            return {"bids":[],"asks":[]}
        with self.assertRaisesRegex(ValueError,"empty_order_book"):
            snapshot_symbol("SOLUSDT",fetch=fetch,clock_ms=lambda:100000)
    def test_missing_notional_fails_closed(self):
        def fetch(path,params=None):
            if path.endswith("exchangeInfo"):
                return {"symbols":[{"symbol":"SOLUSDT","status":"TRADING","contractType":"PERPETUAL","quoteAsset":"USDT","filters":[]}]}
            if path.endswith("24hr"):
                return {"lastPrice":"100","quoteVolume":"25000000"}
            return {"bids":[["99.99","200"]],"asks":[["100.01","200"]]}
        with self.assertRaisesRegex(ValueError,"missing_min_notional"):
            snapshot_symbol("SOLUSDT",fetch=fetch,clock_ms=lambda:100000)

if __name__=="__main__":
    unittest.main()
