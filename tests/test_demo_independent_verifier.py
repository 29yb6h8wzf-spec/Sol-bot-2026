"""Offline independent-verifier tests; no exchange or network access."""
import unittest
from demo_independent_verifier import verify

CANDLE = 600000
NOW = 1000

def payload():
    return {"signal_id": "s-1", "symbol": "XRP/USDT:USDT",
            "strategy": "EMA_ADX", "direction": "long",
            "closed_5m_candle_ms": CANDLE, "score": 100}

def scanner(symbol, *, now_ms):
    return {"symbol": symbol, "status": "RESEARCH_ONLY",
            "closed_5m_candle_ms": CANDLE,
            "candidates_85_plus": [{"strategy": "EMA_ADX",
                                    "direction": "LONG", "score": 85,
                                    "verification": {"independently_checked": True}}]}

class IndependentVerifierTests(unittest.TestCase):
    def test_independent_score_overrides_claimed_score(self):
        p = payload()
        p["score"] = 1
        self.assertEqual(verify(p, scan=scanner, now=NOW)["score"], 85)

    def test_wrong_strategy_fails(self):
        p = payload()
        p["strategy"] = "BREAKOUT"
        with self.assertRaisesRegex(ValueError, "independent_candidate_mismatch"):
            verify(p, scan=scanner, now=NOW)

    def test_wrong_candle_fails(self):
        def wrong(symbol, *, now_ms):
            return {**scanner(symbol, now_ms=now_ms),
                    "closed_5m_candle_ms": CANDLE + 300000}
        with self.assertRaisesRegex(ValueError, "candle_mismatch"):
            verify(payload(), scan=wrong, now=NOW)

    def test_weak_score_fails(self):
        def weak(symbol, *, now_ms):
            result = scanner(symbol, now_ms=now_ms)
            result["candidates_85_plus"][0]["score"] = 84
            return result
        with self.assertRaisesRegex(ValueError, "independent_candidate_mismatch"):
            verify(payload(), scan=weak, now=NOW)

    def test_compact_legacy_signal_recomputed(self):
        p = {"signal_id": "s-1", "symbol": "XRPUSDT",
             "direction": "long", "timestamp": 950, "score": 100}
        result = verify(p, scan=scanner, now=NOW)
        self.assertEqual(result["score"], 85)
        self.assertEqual(result["symbol"], "XRP/USDT:USDT")

    def test_compact_wrong_candle_time_rejected(self):
        p = {"signal_id": "s-1", "symbol": "XRPUSDT",
             "direction": "long", "timestamp": 800}
        with self.assertRaisesRegex(ValueError, "compact_signal_not_at_candle_close"):
            verify(p, scan=scanner, now=NOW)

    def test_compact_ambiguous_candidate_rejected(self):
        p = {"signal_id": "s-1", "symbol": "XRPUSDT",
             "direction": "long", "timestamp": 950}
        def ambiguous(symbol, *, now_ms):
            result = scanner(symbol, now_ms=now_ms)
            result["candidates_85_plus"].append({
                "strategy": "BREAKOUT", "direction": "LONG",
                "score": 90, "verification": {"checked": True}})
            return result
        with self.assertRaisesRegex(ValueError, "independent_candidate_mismatch"):
            verify(p, scan=ambiguous, now=NOW)

    def test_stale_candle_fails(self):
        with self.assertRaisesRegex(ValueError, "stale_candle"):
            verify(payload(), scan=scanner, now=2000)

    def test_scanner_blocked_fails(self):
        def blocked(symbol, *, now_ms):
            return {**scanner(symbol, now_ms=now_ms), "status": "BLOCKED"}
        with self.assertRaisesRegex(ValueError, "scanner_not_ready"):
            verify(payload(), scan=blocked, now=NOW)

if __name__ == "__main__":
    unittest.main()
