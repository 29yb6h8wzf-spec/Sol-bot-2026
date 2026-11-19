import unittest
from futures_engine.research_nonoverlap_outcome_audit import audit


def event(symbol, entry, exit_time, net, strategy="MACD_VOLUME"):
    return {"symbol": symbol, "entry_open_ms": entry, "exit_open_ms": exit_time,
            "net_pct": net, "strategy": strategy, "direction": "LONG"}


class AuditTests(unittest.TestCase):
    def test_overlap_same_symbol_skipped_without_using_returns(self):
        report = {"research_only": True, "execution_authorized": False,
                  "events": [event("SOL", 2, 8, 100),
                             event("SOL", 1, 6, -1),
                             event("XRP", 3, 4, 2),
                             event("SOL", 9, 10, -2)]}
        result = audit(report)
        self.assertEqual(result["nonoverlap"]["count"], 3)
        self.assertEqual(result["overlaps_skipped"], 1)
        self.assertEqual(result["nonoverlap"]["sum_net_pct_uncompounded"], -1)
        self.assertEqual(result["by_symbol"]["SOL"]["count"], 2)

    def test_same_exit_timestamp_cannot_reenter(self):
        result = audit({"research_only": True, "execution_authorized": False,
                        "events": [event("SOL", 1, 2, 1), event("SOL", 2, 4, 1)]})
        self.assertEqual(result["nonoverlap"]["count"], 1)

    def test_research_gate(self):
        with self.assertRaises(ValueError):
            audit({"research_only": False, "execution_authorized": False, "events": []})


if __name__ == "__main__":
    unittest.main()
