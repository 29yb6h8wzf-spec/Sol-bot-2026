import unittest
from futures_engine.research_sqs_preview import preview

CANDLE=1800000000000

def record():
    sid="research-12345678901234567890123456789012"
    return {"signal_id":sid,"symbol":"XRP/USDT:USDT",
            "candle_ms":CANDLE,"state":"PENDING_REVIEW",
            "payload":{"signal_id":sid,"symbol":"XRP/USDT:USDT",
                       "candle_ms":CANDLE,"status":"RECALCULATED_RESEARCH_CANDIDATE",
                       "score_verified_independently":True,
                       "execution_authorized":False,"sqs_sent":False,"orders_sent":False,
                       "score":85,"direction":"LONG"}}

class PreviewTests(unittest.TestCase):
    def test_converts_and_does_not_send(self):
        r=preview(record(),now=(CANDLE+300000)//1000+30)
        p=r["payload"]
        self.assertEqual(p["symbol"],"XRPUSDT")
        self.assertEqual(p["direction"],"long")
        self.assertLessEqual(len(p["signal_id"]),32)
        self.assertFalse(r["authenticated_source"])
    def test_expired(self):
        with self.assertRaisesRegex(ValueError,"expired"):
            preview(record(),now=(CANDLE+300000)//1000+121)
    def test_rejects_future(self):
        with self.assertRaisesRegex(ValueError,"future"):
            preview(record(),now=(CANDLE+300000)//1000-1)
    def test_rejects_forged(self):
        r=record()
        r["payload"]["score_verified_independently"]=False
        with self.assertRaisesRegex(ValueError,"verification"):
            preview(r,now=(CANDLE+300000)//1000+1)
    def test_deterministic(self):
        now=(CANDLE+300000)//1000+1
        self.assertEqual(preview(record(),now=now),preview(record(),now=now))

if __name__=="__main__":
    unittest.main()
