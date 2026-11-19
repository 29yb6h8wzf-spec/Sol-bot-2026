"""Offline demo order planner tests; no exchange access."""
import unittest
from demo_order_planner import plan

BARS = [[i * 300000, 100, 101, 99, 100, 10] for i in range(16)]
NOW = BARS[-1][0] + 300000 + 30000


def verified(direction="long"):
    return {
        "signal_id": "signal-1", "symbol": "XRP/USDT:USDT",
        "source": "verified_85_score_engine", "score": 90,
        "direction": direction, "closed_5m_candle_ms": BARS[-1][0],
        "verification": {"status": "RECALCULATED_RESEARCH_CANDIDATE",
                         "score_verified_independently": True,
                         "execution_authorized": False},
    }


def make(v=None, bars=None, **kwargs):
    return plan(verified() if v is None else v, BARS if bars is None else bars,
                tick=".01", step=".001", min_qty=".001", min_cost="5",
                now_ms=NOW, **kwargs)


class PlannerTests(unittest.TestCase):
    def test_long_risk_and_margin(self):
        p = make()
        self.assertEqual(p["status"], "INDICATIVE_PLAN_ONLY_NOT_EXECUTABLE")
        self.assertLessEqual(float(p["estimated_max_stop_loss_before_fees"]), 1.5)
        self.assertLessEqual(float(p["estimated_notional"]), 15)
        self.assertLess(float(p["stop"]), float(p["entry"]))
        self.assertGreater(float(p["target"]), float(p["entry"]))
        self.assertFalse(p["orders_sent"])

    def test_short_brackets(self):
        p = make(verified("short"))
        self.assertGreater(float(p["stop"]), float(p["entry"]))
        self.assertLess(float(p["target"]), float(p["entry"]))

    def test_claimed_score_does_not_override_proof(self):
        v = verified()
        v["verification"] = {}
        with self.assertRaisesRegex(ValueError, "independent_proof_required"):
            make(v)

    def test_stale_market_fails(self):
        with self.assertRaisesRegex(ValueError, "stale_candle"):
            plan(verified(), BARS, tick=".01", step=".001",
                 min_qty=".001", min_cost="5", now_ms=NOW + 1000000)

    def test_candle_mismatch_fails(self):
        v = verified()
        v["closed_5m_candle_ms"] -= 300000
        with self.assertRaisesRegex(ValueError, "verified_candle_mismatch"):
            make(v)

    def test_margin_cap(self):
        with self.assertRaisesRegex(ValueError, "capital_or_leverage_exceeded"):
            make(leverage=3)

    def test_exchange_minimum(self):
        with self.assertRaisesRegex(ValueError, "below_exchange_minimum"):
            plan(verified(), BARS, tick=".01", step=".001",
                 min_qty="10", min_cost="5", now_ms=NOW)

if __name__ == "__main__":
    unittest.main()
