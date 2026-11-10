"""Offline tests for the fail-closed backtest data exclusion gate."""
import unittest
from backtest_exclusion_gate import validate_manifest,eligible,GAP_START,GAP_END

def manifest():
    return {"status":"PASS_WITH_EXCLUSIONS","months_scanned":48,"fatal_errors":[],"mismatch_count":1,
        "mismatches":[{"symbol":"SOLUSDT","start_ms":1000000,"end_exclusive_ms":1300000,
        "differences":[{"field":"volume","monthly_5m":5,"aggregated_1m":4}]}]}

class ExclusionGateTests(unittest.TestCase):
    def setUp(self):self.intervals=validate_manifest(manifest())
    def test_blocks_missing_day(self):
        self.assertFalse(eligible(self.intervals,"XRPUSDT",GAP_START-60000,GAP_START-1000,GAP_START+60000)[0])
    def test_blocks_lookback_overlap(self):
        self.assertFalse(eligible(self.intervals,"SOLUSDT",999999,1300000,1600000)[0])
    def test_blocks_holding_overlap(self):
        self.assertFalse(eligible(self.intervals,"SOLUSDT",700000,900000,1000001)[0])
    def test_boundary_allowed(self):
        self.assertTrue(eligible(self.intervals,"SOLUSDT",1300000,1600000,1900000)[0])
        self.assertTrue(eligible(self.intervals,"XRPUSDT",GAP_END,GAP_END+60000,GAP_END+120000)[0])
    def test_manifest_rejects_truncated(self):
        m=manifest();m["mismatch_count"]=2
        with self.assertRaises(ValueError):validate_manifest(m)
    def test_manifest_rejects_bad_status(self):
        m=manifest();m["status"]="FAIL"
        with self.assertRaises(ValueError):validate_manifest(m)
    def test_manifest_rejects_missing_evidence(self):
        m=manifest();m["mismatches"][0]["differences"]=[]
        with self.assertRaises(ValueError):validate_manifest(m)
    def test_bad_symbol_and_time_rejected(self):
        with self.assertRaises(ValueError):eligible(self.intervals,"BTCUSDT",1,2,3)
        with self.assertRaises(ValueError):eligible(self.intervals,"SOLUSDT",3,2,1)

if __name__=="__main__":unittest.main()
