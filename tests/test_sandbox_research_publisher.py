import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from futures_engine.sandbox_research_publisher import publish

CANDLE=1800000000000
SID="research-12345678901234567890123456789012"

class FakeSQS:
    def __init__(self): self.messages=[]
    def send_message(self, **kwargs):
        self.messages.append(kwargs)
        return {"MessageId":"fake-id"}

def make_db(path):
    v={"signal_id":SID,"symbol":"XRP/USDT:USDT","candle_ms":CANDLE,
       "status":"RECALCULATED_RESEARCH_CANDIDATE",
       "score_verified_independently":True,"execution_authorized":False,
       "sqs_sent":False,"orders_sent":False,"score":85,"direction":"LONG"}
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE research_outbox (signal_id TEXT PRIMARY KEY, symbol TEXT, candle_ms INTEGER, state TEXT, payload TEXT)")
        db.execute("INSERT INTO research_outbox VALUES (?,?,?,?,?)",
                   (SID,"XRP/USDT:USDT",CANDLE,"PENDING_REVIEW",json.dumps(v)))

class SandboxPublisherTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ, {"SIGNALPILOT_SANDBOX_PUBLISH_ENABLED":"1"})
        self.env.start()
        self.tmp=tempfile.TemporaryDirectory()
        self.db=os.path.join(self.tmp.name,"test.sqlite")
        make_db(self.db)
        self.sqs=FakeSQS()
    def tearDown(self):
        self.tmp.cleanup()
        self.env.stop()
    def test_sends_only_sandbox_research_envelope(self):
        result=publish(db=self.db,sqs=self.sqs,now=(CANDLE+300000)//1000+10)
        self.assertEqual(result["sent"],1)
        body=json.loads(self.sqs.messages[0]["MessageBody"])
        self.assertEqual(body["type"],"SIGNALPILOT_SANDBOX_RESEARCH")
        self.assertFalse(body["orders_enabled"])
        self.assertNotIn("source",body)
    def test_deduplicates_after_success(self):
        now=(CANDLE+300000)//1000+10
        publish(db=self.db,sqs=self.sqs,now=now)
        result=publish(db=self.db,sqs=self.sqs,now=now)
        self.assertEqual(result["already_sent"],1)
        self.assertEqual(len(self.sqs.messages),1)
    def test_ambiguous_send_never_retries(self):
        class BrokenSQS:
            def send_message(self, **kwargs):
                raise TimeoutError("response lost")
        now=(CANDLE+300000)//1000+10
        with self.assertRaises(TimeoutError):
            publish(db=self.db,sqs=BrokenSQS(),now=now)
        result=publish(db=self.db,sqs=self.sqs,now=now)
        self.assertEqual(result["already_sent"],1)
        self.assertEqual(len(self.sqs.messages),0)
        with sqlite3.connect(self.db) as db:
            state=db.execute("SELECT message_id FROM sandbox_publish_log").fetchone()[0]
        self.assertEqual(state,"UNCONFIRMED")
    def test_rejects_expired(self):
        result=publish(db=self.db,sqs=self.sqs,now=(CANDLE+300000)//1000+121)
        self.assertEqual(result["sent"],0)
        self.assertEqual(len(self.sqs.messages),0)

if __name__=="__main__":
    unittest.main()
