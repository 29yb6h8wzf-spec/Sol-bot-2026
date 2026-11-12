import unittest
from signals_v3.discover_current_price_candidates import discover_current_price_candidates,capture_current_candidates

class CurrentCandidateDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.markets=[
            {"symbol":"ADAUSDT","quoteAsset":"USDT","contractType":"PERPETUAL","status":"TRADING"},
            {"symbol":"SOLUSDT","quoteAsset":"USDT","contractType":"PERPETUAL","status":"TRADING"},
            {"symbol":"BTCUSDT","quoteAsset":"USDT","contractType":"PERPETUAL","status":"TRADING"},
            {"symbol":"OLDUSDT","quoteAsset":"USDT","contractType":"PERPETUAL","status":"BREAK"},
        ]
    def fetch(self,path,params=None):
        if path.endswith("exchangeInfo"):
            return {"symbols":[dict(m,filters=[{"filterType":"MIN_NOTIONAL","notional":"5"}]) for m in self.markets]}
        if path.endswith("ticker/price"):
            return [{"symbol":"ADAUSDT","price":"0.99"},{"symbol":"SOLUSDT","price":"150"},{"symbol":"BTCUSDT","price":"90000"},{"symbol":"OLDUSDT","price":"2"}]
        if path.endswith("ticker/24hr"):
            return {"lastPrice":"100","quoteVolume":"25000000"}
        return {"bids":[["99.99","200"]],"asks":[["100.01","200"]]}
    def test_inclusive_price_boundaries(self):
        self.assertEqual(discover_current_price_candidates(self.fetch),("ADAUSDT","SOLUSDT"))
    def test_capture_explicitly_incomplete_when_capped(self):
        result=capture_current_candidates(self.fetch,limit=1,clock_ms=lambda:1000)
        self.assertEqual(result["candidate_count"],2)
        self.assertEqual(result["captured_count"],1)
        self.assertFalse(result["complete_market_capture"])
        self.assertFalse(result["historical_universe_verified"])
    def test_nonfinite_price_fails_closed(self):
        def fetch(path,params=None):
            if path.endswith("ticker/price"):
                return [{"symbol":"ADAUSDT","price":"NaN"},{"symbol":"SOLUSDT","price":"150"},
                        {"symbol":"BTCUSDT","price":"90000"},{"symbol":"OLDUSDT","price":"2"}]
            return self.fetch(path,params)
        with self.assertRaisesRegex(ValueError,"invalid_price_ticker"):
            discover_current_price_candidates(fetch)
    def test_duplicate_market_listing_fails_closed(self):
        self.markets.append(dict(self.markets[0]))
        with self.assertRaisesRegex(ValueError,"duplicate_market_listing"):
            discover_current_price_candidates(self.fetch)
    def test_missing_price_fails_closed(self):
        def fetch(path,params=None):
            if path.endswith("ticker/price"):
                return [{"symbol":"ADAUSDT","price":"1"}]
            return self.fetch(path,params)
        with self.assertRaisesRegex(ValueError,"missing_price_ticker"):
            discover_current_price_candidates(fetch)

if __name__=="__main__":
    unittest.main()
