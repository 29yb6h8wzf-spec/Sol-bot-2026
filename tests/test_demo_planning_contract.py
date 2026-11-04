"""Offline end-to-end contract checks for verified research -> DEMO plan.

No exchange credentials, network requests, or order submission.
"""
import unittest
from decimal import Decimal

from demo_order_planner import plan


def fixture():
    start = 1793700000000
    bars = []
    for i in range(20):
        price = 100 + i * 0.05
        bars.append([start + i * 300000, price, price + 0.5, price - 0.5, price, 1000])
    verified = {
        "symbol": "SOL/USDT:USDT", "source": "verified_85_score_engine",
        "score": 90, "signal_id": "offline-contract-test",
        "direction": "long", "closed_5m_candle_ms": bars[-1][0],
        "verification": {
            "status": "RECALCULATED_RESEARCH_CANDIDATE",
            "score_verified_independently": True,
            "execution_authorized": False,
        },
    }
    return verified, bars, bars[-1][0] + 300000


class DemoPlanningContract(unittest.TestCase):
    def test_verified_candidate_produces_non_executable_bounded_plan(self):
        verified, bars, now = fixture()
        result = plan(verified, bars, tick="0.01", step="0.001",
                      min_qty="0.001", min_cost="5", now_ms=now)
        self.assertEqual(result["status"], "INDICATIVE_PLAN_ONLY_NOT_EXECUTABLE")
        self.assertIs(result["orders_sent"], False)
        self.assertLessEqual(Decimal(result["estimated_max_stop_loss_before_fees"]), Decimal("1.50"))
        self.assertLessEqual(Decimal(result["estimated_notional"]), Decimal("300"))
        self.assertLess(Decimal(result["stop"]), Decimal(result["entry"]))
        self.assertGreater(Decimal(result["target"]), Decimal(result["entry"]))

    def test_unverified_signal_is_rejected(self):
        verified, bars, now = fixture()
        verified["verification"]["score_verified_independently"] = False
        with self.assertRaisesRegex(ValueError, "independent_proof_required"):
            plan(verified, bars, tick="0.01", step="0.001",
                 min_qty="0.001", min_cost="5", now_ms=now)

    def test_below_threshold_is_rejected(self):
        verified, bars, now = fixture()
        verified["score"] = 84
        with self.assertRaisesRegex(ValueError, "score_below_85"):
            plan(verified, bars, tick="0.01", step="0.001",
                 min_qty="0.001", min_cost="5", now_ms=now)

    def test_stale_candle_is_rejected(self):
        verified, bars, now = fixture()
        with self.assertRaisesRegex(ValueError, "stale_candle"):
            plan(verified, bars, tick="0.01", step="0.001",
                 min_qty="0.001", min_cost="5", now_ms=now + 420001)

    def test_leverage_above_two_is_rejected(self):
        verified, bars, now = fixture()
        with self.assertRaisesRegex(ValueError, "capital_or_leverage_exceeded"):
            plan(verified, bars, tick="0.01", step="0.001",
                 min_qty="0.001", min_cost="5", now_ms=now, leverage=3)


if __name__ == "__main__":
    unittest.main()
