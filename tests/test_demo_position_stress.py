"""Offline position stress tests. No order methods exist on fake exchange."""
import unittest
from demo_position_stress import evaluate

NOW = 1793719000


def exposure(symbols=None, pnl="0"):
    symbols = [] if symbols is None else symbols
    return {"source": "binance_demo_account_wide_unrealized_read_only",
            "observed_at": NOW, "exposed_symbols": symbols,
            "open_position_count": len(symbols),
            "unrealized_pnl_usdt": pnl, "orders_sent": False}


def position(qty="1", mark="100", pnl="0", symbol="SOL/USDT:USDT"):
    return {"symbol": symbol, "info": {"positionAmt": qty,
            "markPrice": mark, "unRealizedProfit": pnl}}


class Exchange:
    def __init__(self, rows=None, demo=True):
        self.urls = {"api": {"fapi": "https://demo-fapi.binance.com/fapi"
                             if demo else "https://fapi.binance.com/fapi"}}
        self.rows = [] if rows is None else rows
        self.reads = 0

    def fetch_positions(self):
        self.reads += 1
        return self.rows


class StressTests(unittest.TestCase):
    def test_flat_account(self):
        r = evaluate(Exchange(), exposure(), now=NOW)
        self.assertEqual(r["gross_notional_usdt"], "0")
        self.assertFalse(r["execution_authorized"])

    def test_two_percent_and_five_percent_shocks(self):
        r = evaluate(Exchange([position(qty="-3")]),
                     exposure(["SOL/USDT:USDT"]), now=NOW)
        self.assertEqual(r["gross_notional_usdt"], "300")
        self.assertEqual(r["stress_loss_2pct_usdt"], "6.600")
        self.assertEqual(r["stress_loss_5pct_usdt"], "15.600")
        self.assertTrue(r["stress_5pct_exceeds_daily_cap"])
        self.assertFalse(r["stress_2pct_exceeds_daily_cap"])

    def test_unrealized_crosscheck(self):
        r = evaluate(Exchange([position(pnl="-2")]),
                     exposure(["SOL/USDT:USDT"], "-2"), now=NOW)
        self.assertEqual(r["unrealized_pnl_usdt"], "-2")

    def test_mismatched_pnl_blocks(self):
        with self.assertRaisesRegex(ValueError, "position_observation_mismatch"):
            evaluate(Exchange([position(pnl="-2")]),
                     exposure(["SOL/USDT:USDT"]), now=NOW)

    def test_hedge_legs_block(self):
        with self.assertRaisesRegex(ValueError, "hedge_or_duplicate_position"):
            evaluate(Exchange([position("1"), position("-1")]),
                     exposure(["SOL/USDT:USDT"]), now=NOW)

    def test_nonfinite_price_blocks(self):
        with self.assertRaisesRegex(ValueError, "nonfinite_position_number"):
            evaluate(Exchange([position(mark="NaN")]),
                     exposure(["SOL/USDT:USDT"]), now=NOW)

    def test_live_endpoint_blocks_before_fetch(self):
        ex = Exchange([position()], demo=False)
        with self.assertRaisesRegex(RuntimeError, "non_demo_endpoint_blocked"):
            evaluate(ex, exposure(), now=NOW)
        self.assertEqual(ex.reads, 0)

    def test_stale_observation_blocks(self):
        ex = Exchange()
        with self.assertRaisesRegex(ValueError, "stale_observation"):
            evaluate(ex, exposure(), now=NOW+91)
        self.assertEqual(ex.reads, 0)


if __name__ == "__main__":
    unittest.main()
