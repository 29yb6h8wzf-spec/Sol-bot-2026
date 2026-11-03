import os
import tempfile
import unittest
from futures_engine.research_outbox import stage

def fixture():
    v = {"status":"RECALCULATED_RESEARCH_CANDIDATE",
         "score_verified_independently":True, "execution_authorized":False,
         "sqs_sent":False, "orders_sent":False,
         "symbol":"SOL/USDT:USDT", "candle_ms":123000000,
         "score":90, "strategy":"EMA_ADX", "direction":"LONG",
         "signal_id":"research-test123"}
    return {"status":"RESEARCH_ONLY", "symbol":"SOL/USDT:USDT",
            "closed_5m_candle_ms":123000000,
            "candidates_85_plus":[{"score":90,"strategy":"EMA_ADX",
                                   "direction":"LONG","verification":v}]}

class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name,"test.sqlite3")
    def tearDown(self):
        self.tmp.cleanup()
    def test_stages_once(self):
        self.assertEqual(stage(fixture(),db=self.db),1)
        self.assertEqual(stage(fixture(),db=self.db),0)
    def test_rejects_unverified(self):
        f=fixture()
        f["candidates_85_plus"][0]["verification"]["score_verified_independently"]=False
        with self.assertRaises(ValueError):
            stage(f,db=self.db)
    def test_rejects_mismatched_score(self):
        f=fixture()
        f["candidates_85_plus"][0]["score"]=95
        with self.assertRaises(ValueError):
            stage(f,db=self.db)
    def test_no_candidate_no_stage(self):
        f=fixture()
        f["candidates_85_plus"]=[]
        self.assertEqual(stage(f,db=self.db),0)
    def test_non_research_is_ignored(self):
        f=fixture()
        f["status"]="BLOCKED"
        self.assertEqual(stage(f,db=self.db),0)

if __name__ == "__main__":
    unittest.main()
