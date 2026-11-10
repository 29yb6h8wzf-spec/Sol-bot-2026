import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
from signals_v3.dynamic_universe import UniverseObservation
from signals_v3.historical_universe_gate import load_snapshots,verify_decision_snapshot,COLUMNS

class HistoricalUniverseGateTests(unittest.TestCase):
    def setUp(self):
        self.now=1_000_000
        self.obs=UniverseObservation("ADAUSDT",self.now,1.25,25_000_000,3,20_000,22_000,5,"TRADING","PERPETUAL","USDT")
    def test_complete_snapshot_eligible(self):
        r=verify_decision_snapshot([self.obs],self.now,["ADAUSDT"])
        self.assertEqual(r["eligible_symbols"],("ADAUSDT",))
    def test_missing_listing_rejected(self):
        with self.assertRaisesRegex(ValueError,"missing_historical_market_listing"):
            verify_decision_snapshot([self.obs],self.now)
    def test_incomplete_listing_rejected(self):
        with self.assertRaisesRegex(ValueError,"incomplete_historical_universe"):
            verify_decision_snapshot([self.obs],self.now,["ADAUSDT","SOLUSDT"])
    def test_duplicate_rejected(self):
        with self.assertRaisesRegex(ValueError,"duplicate_symbol_snapshot"):
            verify_decision_snapshot([self.obs,self.obs],self.now,["ADAUSDT"])
    def test_future_snapshot_cannot_qualify(self):
        obs=replace(self.obs,observed_at_ms=self.now+1)
        r=verify_decision_snapshot([obs],self.now,["ADAUSDT"])
        self.assertEqual(r["eligible_symbols"],())
    def test_csv_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"snap.csv"
            p.write_text(",".join(COLUMNS)+"\n"+",".join(str(getattr(self.obs,k)) for k in COLUMNS)+"\n")
            self.assertEqual(load_snapshots(p),(self.obs,))
if __name__=="__main__":unittest.main()
