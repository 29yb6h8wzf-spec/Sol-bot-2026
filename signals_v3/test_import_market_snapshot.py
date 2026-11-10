import json,tempfile,unittest
from pathlib import Path
from signals_v3.import_market_snapshot import import_exchange_info

class ImportMarketSnapshotTests(unittest.TestCase):
    def test_offline_import_keeps_historical_gate_closed(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/"source.json";out=Path(d)/"out.json"
            source.write_text(json.dumps({"symbols":[
                {"symbol":"ADAUSDT","quoteAsset":"USDT","contractType":"PERPETUAL","status":"TRADING","onboardDate":1,"filters":[]},
                {"symbol":"BTCUSDT","quoteAsset":"USDT","contractType":"CURRENT_QUARTER","status":"TRADING"}]}))
            result=import_exchange_info(source,out)
            self.assertEqual([x["symbol"] for x in result["markets"]],["ADAUSDT"])
            self.assertFalse(result["historical_universe_verified"])
            self.assertFalse(result["price_filter_applied"])
            self.assertTrue(out.exists())
    def test_invalid_schema_fails(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/"source.json";source.write_text('{"symbols":{}}')
            with self.assertRaisesRegex(ValueError,"invalid_exchange_info"):
                import_exchange_info(source,Path(d)/"out.json")
if __name__=="__main__":unittest.main()
