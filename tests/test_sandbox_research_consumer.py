import os
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
from futures_engine.sandbox_research_consumer import process, poll_once

def sample():
    return {"type":"SIGNALPILOT_SANDBOX_RESEARCH",
            "research_signal_id":"research-abc123",
            "candidate":{"signal_id":"r-abc123","symbol":"XRPUSDT",
                         "direction":"long","score":85,"timestamp":int(time.time()),
                         "source":"verified_85_score_engine"},
            "execution_authorized":False,"orders_enabled":False}

class FakeSQS:
    def __init__(self, body): self.body=body; self.deleted=[]
    def receive_message(self, **kw):
        return {"Messages":[{"MessageId":"test1","ReceiptHandle":"receipt1",
                             "Body":__import__("json").dumps(self.body)}]}
    def delete_message(self, **kw): self.deleted.append(kw)

class ConsumerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=os.path.join(self.tmp.name,"inbox.sqlite")
        self.env=patch.dict(os.environ,{"SIGNALPILOT_SANDBOX_CONSUME_ENABLED":"1"})
        self.env.start()
    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()
    def test_stores_research(self):
        self.assertEqual(process(sample(),db=self.db),"stored")
    def test_duplicate_is_idempotent(self):
        self.assertEqual(process(sample(),db=self.db),"stored")
        self.assertEqual(process(sample(),db=self.db),"duplicate")
    def test_rejects_orders(self):
        body=sample(); body["orders_enabled"]=True
        with self.assertRaises(ValueError): process(body,db=self.db)
    def test_poll_acknowledges_only_valid(self):
        sqs=FakeSQS(sample())
        self.assertEqual(poll_once(sqs=sqs,db=self.db)["stored"],1)
        self.assertEqual(len(sqs.deleted),1)
    def test_invalid_not_deleted(self):
        body=sample();body["candidate"]["score"]=50
        sqs=FakeSQS(body)
        self.assertEqual(poll_once(sqs=sqs,db=self.db)["rejected"],1)
        self.assertEqual(sqs.deleted,[])

if __name__=="__main__":
    unittest.main()
