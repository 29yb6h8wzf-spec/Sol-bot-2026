"""Offline $150 virtual Binance Demo allocation accounting tests."""
import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from demo_virtual_allocation import compute, run

NOW = int(time.time())
MIDNIGHT = int(datetime.fromtimestamp(NOW, timezone.utc).replace(
    hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)


def fixtures(*, pnl="0", fees="0", unknown=0, owned=0,
             positions=None, orders=0, registry=False):
    positions = [] if positions is None else positions
    attr = {
        "source": "binance_demo_four_symbol_trade_attribution_read_only",
        "observed_at": NOW, "day_start_utc_ms": MIDNIGHT,
        "status": "AUDIT_ONLY_NOT_EXECUTABLE",
        "signalpilot_realized_pnl_usdt": pnl,
        "signalpilot_commissions_usdt": fees,
        "signalpilot_net_before_funding_usdt": str(float(pnl) - float(fees)),
        "signalpilot_fills": owned, "unattributed_fills": unknown,
        "registry_present": registry, "allocation_ledger_reconciled": False,
        "execution_authorized": False, "orders_sent": False,
    }
    account = {
        "source": "binance_demo_observation_only", "observed_at": NOW,
        "usdt_total": "4524", "usdt_free": "4524",
        "exposed_symbols": positions,
        "open_orders": {"XRP/USDT:USDT": orders},
        "open_algo_orders": {"XRP/USDT:USDT": 0},
        "orders_sent": False,
    }
    exposure = {
        "source": "binance_demo_account_wide_unrealized_read_only",
        "observed_at": NOW, "exposed_symbols": positions.copy(),
        "open_position_count": len(positions), "orders_sent": False,
    }
    return attr, account, exposure


class VirtualAllocationTests(unittest.TestCase):
    def test_flat_empty_demo_is_still_not_authorized(self):
        report = compute(*fixtures(), now=NOW)
        self.assertEqual(report["indicative_virtual_balance_before_funding_usdt"], "150.0")
        self.assertFalse(report["allocation_ledger_reconciled"])
        self.assertFalse(report["execution_authorized"])

    def test_owned_realized_profit_less_fees(self):
        report = compute(*fixtures(pnl="2", fees="0.50", owned=1, registry=True), now=NOW)
        self.assertEqual(report["indicative_virtual_balance_before_funding_usdt"], "151.5")
        self.assertEqual(report["verified_commissions_usdt"], "0.50")

    def test_unattributed_fills_flagged(self):
        report = compute(*fixtures(unknown=5), now=NOW)
        self.assertEqual(report["unattributed_fills_today"], 5)
        self.assertIn("UNATTRIBUTED_FILLS", report["block_reasons"])

    def test_open_positions_not_assigned_to_bot(self):
        report = compute(*fixtures(positions=["XRP/USDT:USDT"]), now=NOW)
        self.assertIn("OPEN_POSITION_OWNERSHIP_UNVERIFIED", report["block_reasons"])

    def test_unattributed_open_orders(self):
        report = compute(*fixtures(orders=1), now=NOW)
        self.assertIn("OPEN_ORDER_OWNERSHIP_UNVERIFIED", report["block_reasons"])

    def test_fees_must_reconcile(self):
        a, b, c = fixtures(pnl="2", fees="0.50")
        a["signalpilot_net_before_funding_usdt"] = "2"
        with self.assertRaisesRegex(ValueError, "attribution_accounting_mismatch"):
            compute(a, b, c, now=NOW)

    def test_stale_attribution_rejected(self):
        a, b, c = fixtures()
        a["observed_at"] -= 91
        with self.assertRaisesRegex(ValueError, "stale_observation"):
            compute(a, b, c, now=NOW)

    def test_invalid_day_rejected(self):
        a, b, c = fixtures()
        a["day_start_utc_ms"] -= 86400000
        with self.assertRaisesRegex(ValueError, "allocation_day_mismatch"):
            compute(a, b, c, now=NOW)

    def test_fills_without_registry_rejected(self):
        with self.assertRaisesRegex(ValueError, "fills_without_registry"):
            compute(*fixtures(owned=1), now=NOW)

    def test_nonfinite_money_rejected(self):
        with self.assertRaisesRegex(ValueError, "nonfinite_allocation_amount"):
            compute(*fixtures(pnl="NaN"), now=NOW)

    def test_missing_files_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            report = run(folder)
            self.assertEqual(report["status"], "BLOCKED_INVALID_OR_STALE_INPUT")
            self.assertFalse(report["execution_authorized"])
            self.assertTrue((Path(folder) / "demo-virtual-allocation.json").exists())

    @unittest.skipUnless(os.geteuid() == 0, "requires root")
    def test_root_owned_observations_produce_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, data in zip(
                ("demo-trade-attribution.json", "demo-account-observation.json",
                 "demo-exposure-observation.json"), fixtures(unknown=5)):
                path = root / name
                path.write_text(json.dumps(data))
                path.chmod(0o600)
            report = run(root)
            self.assertEqual(report["unattributed_fills_today"], 5)
            self.assertEqual(report["status"], "BLOCKED_OBSERVATION_ONLY")
            self.assertEqual((root / "demo-virtual-allocation.json").stat().st_mode & 0o077, 0)

    @unittest.skipUnless(os.geteuid() == 0, "requires root")
    def test_world_readable_observation_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, data in zip(
                ("demo-trade-attribution.json", "demo-account-observation.json",
                 "demo-exposure-observation.json"), fixtures()):
                path = root / name
                path.write_text(json.dumps(data))
                path.chmod(0o600)
            (root / "demo-trade-attribution.json").chmod(0o644)
            self.assertEqual(run(root)["status"], "BLOCKED_INVALID_OR_STALE_INPUT")

if __name__ == "__main__":
    unittest.main()
