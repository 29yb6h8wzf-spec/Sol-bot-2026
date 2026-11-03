"""Offline tests for persistent Binance Demo UTC rollover reconciliation."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from demo_reconciliation_guard import reconcile, run

DAY = int(datetime(2026, 11, 3, tzinfo=timezone.utc).timestamp())
NOW = DAY + 12 * 3600
START = DAY * 1000


def fixtures(now=NOW, *, unknown=0, realized="0", fees="0", funding="0",
             owned_realized="0", owned_fees="0", exposed=False):
    start = int(datetime.fromtimestamp(now, timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    pnl = {"source": "binance_demo_account_wide_income_read_only",
           "observed_at": now, "day_start_utc_ms": start,
           "realized_pnl_usdt": realized, "commissions_usdt": fees,
           "funding_usdt": funding,
           "net_income_usdt": str(__import__("decimal").Decimal(realized) +
                                  __import__("decimal").Decimal(fees) +
                                  __import__("decimal").Decimal(funding)),
           "orders_sent": False}
    attr = {"source": "binance_demo_four_symbol_trade_attribution_read_only",
            "observed_at": now, "day_start_utc_ms": start,
            "status": "AUDIT_ONLY_NOT_EXECUTABLE",
            "signalpilot_realized_pnl_usdt": owned_realized,
            "signalpilot_commissions_usdt": owned_fees,
            "signalpilot_net_before_funding_usdt": str(
                __import__("decimal").Decimal(owned_realized) -
                __import__("decimal").Decimal(owned_fees)),
            "signalpilot_fills": 0, "unattributed_fills": unknown,
            "allocation_ledger_reconciled": False,
            "execution_authorized": False, "orders_sent": False}
    syms = ["BTC/USDT:USDT"] if exposed else []
    account = {"source": "binance_demo_observation_only",
               "observed_at": now, "exposed_symbols": syms,
               "open_orders": {"BTC/USDT:USDT": 0},
               "open_algo_orders": {"BTC/USDT:USDT": 0},
               "orders_sent": False}
    exposure = {"source": "binance_demo_account_wide_unrealized_read_only",
                "observed_at": now, "exposed_symbols": syms,
                "open_position_count": len(syms), "orders_sent": False}
    return pnl, attr, account, exposure


class ReconciliationTests(unittest.TestCase):
    def test_flat_account_is_still_blocked(self):
        status, state = reconcile(*fixtures(), now=NOW)
        self.assertEqual(status["status"], "BLOCKED_UNRECONCILED")
        self.assertFalse(status["prior_day_exposure_unresolved"])
        self.assertFalse(status["execution_authorized"])

    def test_income_gaps_and_funding_remain_unattributed(self):
        status, _ = reconcile(*fixtures(realized="-2", fees="-0.3",
                                        funding="-0.1"), now=NOW)
        self.assertEqual(status["account_realized_gap_usdt"], "-2")
        self.assertEqual(status["account_commission_gap_usdt"], "-0.3")
        self.assertEqual(status["account_funding_unattributed_usdt"], "-0.1")
        self.assertIn("FUNDING_NOT_ATTRIBUTED_TO_STRATEGY", status["block_reasons"])

    def test_unattributed_fills_persist_across_midnight(self):
        _, state = reconcile(*fixtures(unknown=5), now=NOW)
        tomorrow = DAY + 86400 + 60
        status, state = reconcile(*fixtures(tomorrow), state, now=tomorrow)
        self.assertTrue(status["unattributed_history_unresolved"])
        self.assertTrue(status["monitoring_gap_unresolved"])
        self.assertFalse(status["execution_authorized"])

    def test_prior_day_open_position_stays_latched_after_close(self):
        before = DAY + 86350
        _, state = reconcile(*fixtures(before, exposed=True), now=before)
        after = DAY + 86400 + 30
        status, state = reconcile(*fixtures(after), state, now=after)
        self.assertTrue(status["prior_day_exposure_unresolved"])
        self.assertFalse(status["open_exposure_now"])
        _, state = reconcile(*fixtures(after + 60), state, now=after + 60)
        self.assertTrue(state["prior_day_exposure_unresolved"])

    def test_prior_day_flat_does_not_claim_carryover(self):
        before = DAY + 86350
        _, state = reconcile(*fixtures(before), now=before)
        after = DAY + 86400 + 30
        status, _ = reconcile(*fixtures(after), state, now=after)
        self.assertFalse(status["prior_day_exposure_unresolved"])
        self.assertFalse(status["monitoring_gap_unresolved"])

    def test_first_observation_with_open_position_is_unverified(self):
        status, _ = reconcile(*fixtures(exposed=True), now=NOW)
        self.assertTrue(status["prior_day_exposure_unresolved"])

    def test_long_monitor_gap_latches(self):
        _, state = reconcile(*fixtures(), now=NOW)
        status, state = reconcile(*fixtures(NOW+1000), state, now=NOW+1000)
        self.assertTrue(status["monitoring_gap_unresolved"])
        status, _ = reconcile(*fixtures(NOW+1060), state, now=NOW+1060)
        self.assertTrue(status["monitoring_gap_unresolved"])

    def test_stale_income_blocks(self):
        docs = list(fixtures())
        docs[0]["observed_at"] -= 91
        with self.assertRaisesRegex(ValueError, "stale_observation"):
            reconcile(*docs, now=NOW)

    def test_wrong_income_day_blocks(self):
        docs = list(fixtures())
        docs[0]["day_start_utc_ms"] -= 86400000
        with self.assertRaisesRegex(ValueError, "income_and_fills_day_mismatch"):
            reconcile(*docs, now=NOW)

    def test_bad_prior_state_blocks(self):
        with self.assertRaisesRegex(ValueError, "untrusted_previous_reconciliation"):
            reconcile(*fixtures(), {}, now=NOW)

    def test_mismatched_positions_block(self):
        docs = list(fixtures(exposed=True))
        docs[3]["exposed_symbols"] = []
        with self.assertRaisesRegex(ValueError, "inconsistent_open_positions"):
            reconcile(*docs, now=NOW)

    def test_invalid_income_totals_block(self):
        docs = list(fixtures(realized="-1"))
        docs[0]["net_income_usdt"] = "0"
        with self.assertRaisesRegex(ValueError, "inconsistent_income_totals"):
            reconcile(*docs, now=NOW)

    @unittest.skipUnless(os.geteuid() == 0, "root-owned files required")
    def test_state_persists_and_untrusted_state_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            names = ("demo-pnl-observation.json", "demo-trade-attribution.json",
                     "demo-account-observation.json", "demo-exposure-observation.json")
            for name, obj in zip(names, fixtures(unknown=5)):
                p = root / name
                p.write_text(json.dumps(obj))
                p.chmod(0o600)
            first = run(root, now=NOW)
            self.assertTrue(first["unattributed_history_unresolved"])
            state = root / "demo-reconciliation-state.json"
            self.assertEqual(state.stat().st_mode & 0o077, 0)
            state.chmod(0o644)
            second = run(root, now=NOW+10)
            self.assertEqual(second["status"], "BLOCKED_INVALID_OR_STALE_INPUT")
            self.assertFalse(second["execution_authorized"])


if __name__ == "__main__":
    unittest.main()
