"""Offline tests: Binance Demo PnL observer never trades."""
import unittest
from datetime import datetime, timezone
from demo_pnl_observer import observe, fetch_utc_day_income, summarize

NOW = int(datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc).timestamp() * 1000)
START = int(datetime(2026, 11, 3, tzinfo=timezone.utc).timestamp() * 1000)


def event(kind, amount, tx, *, timestamp=START + 1000, asset="USDT"):
    return {"incomeType": kind, "income": str(amount), "tranId": tx,
            "time": timestamp, "asset": asset}


class Demo:
    def __init__(self, batches=None, demo=True):
        self.urls = {"api": {"fapi": "https://demo-fapi.binance.com/fapi"
                             if demo else "https://fapi.binance.com/fapi"}}
        self.batches = batches if batches is not None else [[]]
        self.calls = []
    def fapiPrivateGetIncome(self, params):
        self.calls.append(params)
        return self.batches[len(self.calls)-1]


class PnLTests(unittest.TestCase):
    def test_empty_day_is_observation_not_approval(self):
        x = Demo()
        result = observe(x, now_ms=NOW)
        self.assertEqual(result["net_income_usdt"], "0")
        self.assertEqual(x.calls[0]["startTime"], START)
        self.assertFalse(result["risk_snapshot_approved"])
        self.assertFalse(result["orders_sent"])

    def test_losses_include_fees_and_funding(self):
        x = Demo([[event("REALIZED_PNL", "-7", 1),
                   event("COMMISSION", "-0.3", 2),
                   event("FUNDING_FEE", "-0.2", 3)]])
        result = observe(x, now_ms=NOW)
        self.assertEqual(result["net_income_usdt"], "-7.5")
        self.assertTrue(result["daily_loss_threshold_reached"])

    def test_profits_do_not_approve_trading(self):
        x = Demo([[event("REALIZED_PNL", "20", 1)]])
        result = observe(x, now_ms=NOW)
        self.assertFalse(result["allocation_ledger_reconciled"])
        self.assertFalse(result["execution_authorized"])

    def test_live_endpoint_blocked_before_request(self):
        x = Demo(demo=False)
        with self.assertRaisesRegex(RuntimeError, "non_demo_endpoint_blocked"):
            observe(x, now_ms=NOW)
        self.assertEqual(x.calls, [])

    def test_non_usdt_income_blocks(self):
        with self.assertRaisesRegex(ValueError, "unsupported_income_event_or_asset"):
            observe(Demo([[event("REALIZED_PNL", "2", 1, asset="BNB")]]), now_ms=NOW)

    def test_unknown_income_type_blocks(self):
        with self.assertRaisesRegex(ValueError, "unsupported_income_event_or_asset"):
            observe(Demo([[event("TRANSFER", "200", 1)]]), now_ms=NOW)

    def test_duplicate_income_blocks(self):
        e = event("COMMISSION", "-1", 7)
        with self.assertRaisesRegex(ValueError, "duplicate_income_event"):
            observe(Demo([[e, e]]), now_ms=NOW)

    def test_out_of_day_income_blocks(self):
        with self.assertRaisesRegex(ValueError, "income_outside_requested_day"):
            observe(Demo([[event("COMMISSION", "-1", 1, timestamp=START-1)]]),
                    now_ms=NOW)

    def test_pages_and_day_boundaries(self):
        x = Demo([[event("COMMISSION", "-1", 1),
                   event("COMMISSION", "-1", 2)],
                  [event("FUNDING_FEE", "0.1", 3)]])
        result = observe(x, now_ms=NOW, page_size=2)
        self.assertEqual(result["net_income_usdt"], "-1.9")
        self.assertEqual([c["page"] for c in x.calls], [1, 2])

    def test_nonfinite_amount_blocks(self):
        with self.assertRaisesRegex(ValueError, "nonfinite_income_amount"):
            observe(Demo([[event("COMMISSION", "NaN", 1)]]), now_ms=NOW)

if __name__ == "__main__":
    unittest.main()
