import json
import tempfile
import unittest
from pathlib import Path
from signals_v3.persist_current_capture import append_current_capture

class CapturePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.capture={"current_only":True,"historical_universe_verified":False,
                      "candidate_count":2,"captured_count":1,
                      "complete_market_capture":False,
                      "snapshots":[{"symbol":"SOLUSDT","observed_at_ms":1000,
                                    "current_only":True,"historical_universe_verified":False}]}
    def test_append_two_independent_records(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"snapshots.jsonl"
            append_current_capture(path,self.capture)
            append_current_capture(path,self.capture)
            records=[json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(len(records),2)
            self.assertFalse(records[0]["complete_market_capture"])
    def test_reject_false_completeness(self):
        self.capture["complete_market_capture"]=True
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,"false_complete_market_claim"):
                append_current_capture(Path(directory)/"x.jsonl",self.capture)
    def test_reject_historical_mislabeling(self):
        self.capture["historical_universe_verified"]=True
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,"invalid_current_capture_provenance"):
                append_current_capture(Path(directory)/"x.jsonl",self.capture)

if __name__=="__main__":
    unittest.main()
