import unittest
from unittest.mock import patch
from futures_engine.verified_strategy_scan import evaluate

STEP = {"5m": 300000, "4h": 14400000}
BASE = 1728000000000
END = BASE + 110*STEP["4h"]

class DummyExchange:
    closed = False
    def close(self):
        self.closed = True

def loader(symbol, timeframe):
    step = STEP[timeframe]
    bars = [[END - (110-i)*step, 100, 102, 99, 100+i*0.01, 10]
            for i in range(110)]
    return DummyExchange(), {}, bars

class StrategyScanTests(unittest.TestCase):
    def test_high_score_is_research_only(self):
        with patch("futures_engine.verified_strategy_scan.candidates",
                   return_value=([{"strategy":"EMA_ADX","direction":"LONG",
                                   "score":90,"reason":"test"}], {})):
            result = evaluate("SOL/USDT:USDT", loader=loader,
                              now_ms=END + 1000)
        self.assertEqual(len(result["candidates_85_plus"]), 1)
        self.assertFalse(result["score_verified_independently"])
        self.assertFalse(result["sqs_sent"])
        self.assertFalse(result["orders_sent"])

    def test_low_score_filtered(self):
        with patch("futures_engine.verified_strategy_scan.candidates",
                   return_value=([{"strategy":"EMA_ADX","direction":"LONG",
                                   "score":84,"reason":"test"}], {})):
            result = evaluate("SOL/USDT:USDT", loader=loader,
                              now_ms=BASE + 110*STEP["4h"] + 1000)
        self.assertEqual(result["candidates_85_plus"], [])

    def test_reject_unsupported_symbol(self):
        with self.assertRaisesRegex(ValueError, "unsupported"):
            evaluate("BNB/USDT:USDT", loader=loader)

    def test_reject_stale_data(self):
        with self.assertRaisesRegex(ValueError, "stale"):
            evaluate("SOL/USDT:USDT", loader=loader,
                     now_ms=END + 2*STEP["4h"] + 200000)

if __name__ == "__main__":
    unittest.main()
