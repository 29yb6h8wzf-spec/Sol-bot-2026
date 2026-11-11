import unittest
from signals_v2.hybrid import Hypothesis
from signals_v2.contracts import Candle
from signals_v2.replay import replay
from signals_v3.cost_decomposition import decompose, summarize

FIVE = 300000


def bars(rows, start=FIVE * 10):
    return tuple(Candle(start + i * FIVE, o, h, l, c, 1.0, start + (i + 1) * FIVE)
                 for i, (o, h, l, c) in enumerate(rows))


def record_for(direction, stop, target, future):
    proposal = Hypothesis("signals.v3.research.1", "SOLUSDT", direction, "trend_pullback",
                          "V3_EXPLORATORY", future[0].open_ms, 100.0, stop, target,
                          future[0].open_ms + 600000)
    result = replay(proposal, future, funding_rate_total=0.0001)
    return {"month": "2026-01", "symbol": "SOLUSDT", "strategy": "trend_pullback",
            "direction": direction, "exit_reason": result.exit_reason,
            "bars_held": result.bars_held, "reference_open": future[0].open, "stop": stop,
            "entry_fill": result.entry_fill, "exit_fill": result.exit_fill,
            "net_r": result.net_r, "fee_r": result.fee_r, "funding_r": result.funding_r}


class CostDecompositionTests(unittest.TestCase):
    def test_components_sum_to_net_for_long_target(self):
        rec = record_for("LONG", 99.0, 102.0, bars([(100, 103, 99.5, 102.5)]))
        row = decompose(rec)
        self.assertEqual(row["exit_reason"], "TARGET")
        self.assertAlmostEqual(row["raw_r"] - row["slippage_r"] - row["fee_r"] - row["funding_r"],
                               row["net_r"], places=9)
        self.assertGreater(row["slippage_r"], 0)
        self.assertAlmostEqual(row["raw_r"], 2.0 / (100 * 1.0002 - 99.0), places=6)

    def test_components_sum_to_net_for_short_stop(self):
        rec = record_for("SHORT", 101.0, 98.0, bars([(100, 101.5, 99.8, 101.2)]))
        row = decompose(rec)
        self.assertEqual(row["exit_reason"], "STOP")
        self.assertAlmostEqual(row["raw_r"] - row["slippage_r"] - row["fee_r"] - row["funding_r"],
                               row["net_r"], places=9)

    def test_tight_stop_makes_costs_dominate(self):
        tight = decompose(record_for("LONG", 99.8, 100.4, bars([(100, 100.5, 99.9, 100.45)])))
        wide = decompose(record_for("LONG", 98.0, 104.0, bars([(100, 104.5, 99.0, 104.2)])))
        self.assertGreater(tight["round_trip_cost_r"], 3 * wide["round_trip_cost_r"])

    def test_inconsistent_record_rejected(self):
        rec = record_for("LONG", 99.0, 102.0, bars([(100, 103, 99.5, 102.5)]))
        rec["net_r"] += 0.5
        with self.assertRaisesRegex(ValueError, "inconsistent_trade_decomposition"):
            decompose(rec)

    def test_summary_is_never_certification(self):
        rows = [decompose(record_for("LONG", 99.0, 102.0, bars([(100, 103, 99.5, 102.5)])))] * 3
        result = summarize(rows)
        self.assertFalse(result["out_of_sample_certified"])
        self.assertFalse(result["profitability_proven"])
        self.assertTrue(result["window_previously_inspected"])
        self.assertEqual(result["overall"]["trades"], 3)

    def test_empty_summary_insufficient(self):
        self.assertEqual(summarize([])["diagnosis"], "INSUFFICIENT_DATA")


if __name__ == "__main__":
    unittest.main()
