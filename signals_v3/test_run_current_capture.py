import json
import tempfile
import unittest
from pathlib import Path
from signals_v3.run_current_capture import run_one_shot

class OneShotCaptureTests(unittest.TestCase):
    def fetch(self,path,params=None):
        if path.endswith("exchangeInfo"):
            return {"symbols":[{"symbol":"SOLUSDT","status":"TRADING",
                    "contractType":"PERPETUAL","quoteAsset":"USDT",
                    "filters":[{"filterType":"MIN_NOTIONAL","notional":"5"}]}]}
        if path.endswith("ticker/price"):
            return [{"symbol":"SOLUSDT","price":"100"}]
        if path.endswith("ticker/24hr"):
            return {"lastPrice":"100","quoteVolume":"25000000"}
        if path.endswith("depth"):
            return {"bids":[["99.99","200"]],"asks":[["100.01","200"]]}
        raise AssertionError(path)
    def test_one_shot_persists_complete_current_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"market.jsonl"
            result=run_one_shot(path,fetch=self.fetch,limit=1,clock_ms=lambda:1000)
            self.assertEqual(result["captured_count"],1)
            self.assertTrue(result["complete_market_capture"])
            record=json.loads(path.read_text().splitlines()[0])
            self.assertTrue(record["current_only"])
            self.assertFalse(record["historical_universe_verified"])
            self.assertEqual(record["snapshots"][0]["symbol"],"SOLUSDT")

if __name__=="__main__":
    unittest.main()
