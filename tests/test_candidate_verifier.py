import unittest
from unittest.mock import patch
from futures_engine.candidate_verifier import verify_candidate, VerificationError

def bars(step):
    return [{"time": i*step, "high": 102, "low": 98,
             "close": 100, "volume": 10} for i in range(110)]

CANDIDATE = {"strategy": "EMA_ADX", "direction": "LONG", "score": 90}
SYMBOL = "SOL/USDT:USDT"

class CandidateVerifierTests(unittest.TestCase):
    @patch("futures_engine.candidate_verifier.candidates")
    def test_recalculates_and_is_non_executable(self, mock):
        mock.return_value = ([dict(CANDIDATE)], {})
        a = verify_candidate(CANDIDATE, symbol=SYMBOL,
                             five=bars(300000), four=bars(14400000))
        b = verify_candidate(CANDIDATE, symbol=SYMBOL,
                             five=bars(300000), four=bars(14400000))
        self.assertEqual(a["signal_id"], b["signal_id"])
        self.assertTrue(a["score_verified_independently"])
        self.assertFalse(a["execution_authorized"])
        self.assertFalse(a["sqs_sent"])
        self.assertFalse(a["orders_sent"])

    @patch("futures_engine.candidate_verifier.candidates")
    def test_rejects_forged_score(self, mock):
        mock.return_value = ([dict(CANDIDATE, score=84)], {})
        with self.assertRaisesRegex(VerificationError, "does not match"):
            verify_candidate(CANDIDATE, symbol=SYMBOL,
                             five=bars(300000), four=bars(14400000))

    def test_rejects_gaps(self):
        five = bars(300000)
        five[-1]["time"] += 300000
        with self.assertRaisesRegex(VerificationError, "gaps"):
            verify_candidate(CANDIDATE, symbol=SYMBOL,
                             five=five, four=bars(14400000))

    def test_rejects_low_score(self):
        with self.assertRaisesRegex(VerificationError, "score"):
            verify_candidate(dict(CANDIDATE, score=70), symbol=SYMBOL,
                             five=bars(300000), four=bars(14400000))

    def test_rejects_unknown_symbol(self):
        with self.assertRaisesRegex(VerificationError, "unsupported"):
            verify_candidate(CANDIDATE, symbol="BNB/USDT:USDT",
                             five=bars(300000), four=bars(14400000))

if __name__ == "__main__":
    unittest.main()
