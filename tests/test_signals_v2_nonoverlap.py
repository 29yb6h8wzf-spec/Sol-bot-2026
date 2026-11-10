"""Non-overlap diagnostic must fail closed and remain deterministic."""
from dataclasses import replace
import unittest
from signals_v2.hybrid import Hypothesis
from signals_v2.nonoverlap import select_nonoverlapping


def proposal(symbol, ms, specialist="trend_continuation"):
    return Hypothesis("signals.v2.research.1", symbol, "LONG", specialist,
                      "TREND", ms, 100.0, 99.0, 102.0, ms + 600_000)


class NonOverlapTests(unittest.TestCase):
    def test_same_symbol_suppressed_during_horizon(self):
        p = [proposal("SOLUSDT", 100), proposal("SOLUSDT", 200),
             proposal("SOLUSDT", 14_400_100)]
        self.assertEqual(select_nonoverlapping(p), (p[0], p[2]))

    def test_cross_symbol_independent(self):
        p = [proposal("SOLUSDT", 100), proposal("XRPUSDT", 100)]
        self.assertEqual(len(select_nonoverlapping(p)), 2)

    def test_deterministic_order(self):
        p = [proposal("SOLUSDT", 200), proposal("SOLUSDT", 100)]
        self.assertEqual(select_nonoverlapping(p), (p[1],))

    def test_duplicate_rejected(self):
        p = proposal("SOLUSDT", 100)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            select_nonoverlapping((p, p))

    def test_execution_authorized_rejected(self):
        with self.assertRaisesRegex(ValueError, "research_only"):
            select_nonoverlapping((replace(proposal("SOLUSDT", 100),
                                            execution_authorized=True),))

    def test_invalid_horizon(self):
        with self.assertRaises(ValueError):
            select_nonoverlapping((), holding_ms=0)


if __name__ == "__main__":
    unittest.main()
