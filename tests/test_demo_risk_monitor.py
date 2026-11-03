"""Offline tests of read-only Binance Demo account-wide loss monitor."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from demo_risk_monitor import assess, run

NOW = int(datetime(2026, 11, 3, 15, tzinfo=timezone.utc).timestamp())
START = int(datetime(2026, 11, 3, tzinfo=timezone.utc).timestamp() * 1000)


def fixtures(realized="0", unrealized="0", symbols=None):
    symbols = [] if symbols is None else symbols
    pnl = {"source": "binance_demo_account_wide_income_read_only",
           "observed_at": NOW, "day_start_utc_ms": START,
           "net_income_usdt": realized, "orders_sent": False}
    exposure = {"source": "binance_demo_account_wide_unrealized_read_only",
                "observed_at": NOW, "unrealized_pnl_usdt": unrealized,
                "open_position_count": len(symbols),
                "exposed_symbols": symbols, "orders_sent": False}
    account = {"source": "binance_demo_observation_only",
               "observed_at": NOW, "exposed_symbols": symbols.copy(),
               "open_orders": {"XRP/USDT:USDT": 0},
               "open_algo_orders": {"XRP/USDT:USDT": 0},
               "orders_sent": False}
    return pnl, exposure, account


class RiskMonitorTests(unittest.TestCase):
    def test_flat_account_still_blocked(self):
        status, state = assess(*fixtures(), now=NOW)
        self.assertEqual(status["reason"], "ALLOCATION_LEDGER_NOT_RECONCILED")
        self.assertFalse(status["execution_authorized"])
        self.assertFalse(state["latched"])

    def test_combined_realized_unrealized_loss(self):
        status, state = assess(*fixtures("-1", "-6.5", ["XRP/USDT:USDT"]), now=NOW)
        self.assertEqual(status["reason"], "DAILY_LOSS_KILL_SWITCH")
        self.assertTrue(state["latched"])

    def test_high_water_drawdown_latches(self):
        _, state = assess(*fixtures("10"), now=NOW)
        status, state = assess(*fixtures("2"), state, now=NOW)
        self.assertEqual(state["worst_drawdown_usdt"], "8")
        self.assertEqual(status["reason"], "DAILY_LOSS_KILL_SWITCH")

    def test_latch_survives_recovery(self):
        _, state = assess(*fixtures("-8"), now=NOW)
        status, state = assess(*fixtures("1"), state, now=NOW)
        self.assertTrue(state["latched"])
        self.assertEqual(status["reason"], "DAILY_LOSS_KILL_SWITCH")

    def test_wrong_position_symbols_fail(self):
        p, e, a = fixtures("0", "0", ["XRP/USDT:USDT"])
        a["exposed_symbols"] = ["ETH/USDT:USDT"]
        with self.assertRaisesRegex(ValueError, "exposure_observations_disagree"):
            assess(p, e, a, now=NOW)

    def test_open_order_blocks(self):
        p, e, a = fixtures()
        a["open_orders"]["XRP/USDT:USDT"] = 1
        status, _ = assess(p, e, a, now=NOW)
        self.assertEqual(status["reason"], "UNATTRIBUTED_ACCOUNT_EXPOSURE")

    def test_stale_observation_fails(self):
        p, e, a = fixtures()
        e["observed_at"] -= 91
        with self.assertRaisesRegex(ValueError, "stale_observation"):
            assess(p, e, a, now=NOW)

    def test_live_source_fails(self):
        p, e, a = fixtures()
        p["source"] = "binance_live"
        with self.assertRaisesRegex(ValueError, "untrusted_observation_source"):
            assess(p, e, a, now=NOW)

    def test_nan_fails(self):
        with self.assertRaisesRegex(ValueError, "nonfinite_decimal"):
            assess(*fixtures("NaN"), now=NOW)

    def test_missing_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            status = run(folder)
            self.assertEqual(status["reason"], "MISSING_OR_INVALID_OBSERVATION")
            self.assertFalse(status["execution_authorized"])
            self.assertTrue((Path(folder) / "demo-risk-monitor-status.json").exists())

if __name__ == "__main__":
    unittest.main()
