"""Offline replay tests: closed 4h alignment, missing history, fail closed."""
import unittest
from unittest.mock import patch

from futures_engine.research_closed_candle_score_replay import (
    replay_symbol, replay_report, FIVE_MS, FOUR_MS,
)


def bars(count, step, price=100):
    return [[i * step, price, price + 1, price - 1, price, 10] for i in range(count)]


class ClosedCandleScoreReplayTests(unittest.TestCase):
    def test_only_closed_four_hour_bars_used(self):
        five = bars(240, FIVE_MS)
        four = bars(110, FOUR_MS)
        # Shift 5m candles to start after 100 complete 4h bars.
        for row in five:
            row[0] += 100 * FOUR_MS
        captured = []

        def fake_candidates(five_rows, four_rows):
            captured.append((five_rows[-1]["time"], four_rows[-1]["time"]))
            return ([{"strategy": "RSI_BOLL", "direction": "LONG", "score": 80}], {})

        with patch("futures_engine.research_closed_candle_score_replay.candidates", side_effect=fake_candidates):
            result = replay_symbol("SOL/USDT:USDT", five, four)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["setups"][0]["score"], 80)
        for last_five_open, last_four_open in captured:
            self.assertLessEqual(last_four_open + FOUR_MS, last_five_open + FIVE_MS)

    def test_gap_and_invalid_symbol_rejected(self):
        five = bars(240, FIVE_MS)
        four = bars(110, FOUR_MS)
        five[5][0] += FIVE_MS
        with self.assertRaises(ValueError):
            replay_symbol("SOL/USDT:USDT", five, four)
        with self.assertRaises(ValueError):
            replay_symbol("BTC/USDT:USDT", bars(240, FIVE_MS), four)

    def test_insufficient_history_rejected(self):
        with self.assertRaises(ValueError):
            replay_report({"XRP/USDT:USDT": {"5m": bars(240, FIVE_MS),
                                             "4h": bars(2, FOUR_MS)}})


if __name__ == "__main__":
    unittest.main()
