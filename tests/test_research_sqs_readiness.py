import json
import os
import sqlite3
import tempfile
import unittest
from futures_engine.research_sqs_readiness import audit

class ReadinessTests(unittest.TestCase):
    def test_missing_database_is_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            r=audit(db=os.path.join(d,"missing.sqlite"))
        self.assertEqual(r["status"],"BLOCKED")
    def test_expired_candidate_is_not_publishable(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,"test.sqlite")
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE research_outbox (signal_id TEXT,symbol TEXT,candle_ms INTEGER,state TEXT,payload TEXT)")
                db.execute("INSERT INTO research_outbox VALUES(?,?,?,?,?)",
                    ("research-test","XRP/USDT:USDT",1800000000000,
                     "PENDING_REVIEW",json.dumps({"signal_id":"research-test"})))
            r=audit(db=path,now=1900000000)
        self.assertEqual(r["fresh_previewable"],0)
        self.assertEqual(r["expired_or_future"],0)
        self.assertEqual(r["invalid_or_not_pending"],1)
        self.assertFalse(r["sqs_sent"])

if __name__=="__main__":
    unittest.main()
