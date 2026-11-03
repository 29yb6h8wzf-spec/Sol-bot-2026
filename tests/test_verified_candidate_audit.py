import unittest
from futures_engine.verified_candidate_audit import audit_candidate

T = 1800000000000
STEP = 900000

def bars():
    return [[T + i * STEP, 1, 2, 1, 1.5, 10] for i in range(3)]

class CandidateAuditTests(unittest.TestCase):
    def test_valid_candidate_never_executes(self):
        r = audit_candidate("SOL/USDT:USDT", bars(), "long", now_ms=T + 3 * STEP + 1000)
        self.assertFalse(r["sqs_sent"])
        self.assertFalse(r["orders_sent"])
        self.assertFalse(r["score_verified_independently"])

    def test_unfinished_candle(self):
        with self.assertRaisesRegex(ValueError, "unfinished"):
            audit_candidate("SOL/USDT:USDT", bars(), "short", now_ms=T + 2 * STEP + 1000)

    def test_stale_candle(self):
        with self.assertRaisesRegex(ValueError, "stale"):
            audit_candidate("SOL/USDT:USDT", bars(), "short", now_ms=T + 5 * STEP + 200000)

    def test_missing_candle(self):
        x = bars()
        x[1][0] += STEP
        with self.assertRaisesRegex(ValueError, "noncontiguous"):
            audit_candidate("SOL/USDT:USDT", x, "long", now_ms=T + 3 * STEP + 1000)

    def test_unknown_market(self):
        with self.assertRaisesRegex(ValueError, "unsupported"):
            audit_candidate("BNB/USDT:USDT", bars(), "long", now_ms=T + 3 * STEP + 1000)

if __name__ == "__main__":
    unittest.main()
