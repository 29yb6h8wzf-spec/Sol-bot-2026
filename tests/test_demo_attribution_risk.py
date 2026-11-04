"""Read-only risk monitor integration with trade attribution audit."""
import json
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from demo_risk_monitor import run


class AttributionRiskTests(unittest.TestCase):
    def test_unattributed_exchange_fills_keep_monitor_blocked(self):
        now = int(time.time())
        start = int(datetime.fromtimestamp(now, timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = {
                "demo-pnl-observation.json": {
                    "source": "binance_demo_account_wide_income_read_only",
                    "observed_at": now, "day_start_utc_ms": start,
                    "net_income_usdt": "-0.01", "orders_sent": False},
                "demo-exposure-observation.json": {
                    "source": "binance_demo_account_wide_unrealized_read_only",
                    "observed_at": now, "unrealized_pnl_usdt": "0",
                    "open_position_count": 0, "exposed_symbols": [],
                    "orders_sent": False},
                "demo-account-observation.json": {
                    "source": "binance_demo_observation_only",
                    "observed_at": now, "exposed_symbols": [],
                    "open_orders": {"XRP/USDT:USDT": 0},
                    "open_algo_orders": {"XRP/USDT:USDT": 0},
                    "orders_sent": False},
                "demo-trade-attribution.json": {
                    "source": "binance_demo_four_symbol_trade_attribution_read_only",
                    "observed_at": now, "day_start_utc_ms": start,
                    "unattributed_fills": 5, "signalpilot_fills": 0,
                    "allocation_ledger_reconciled": False,
                    "execution_authorized": False, "orders_sent": False},
                "demo-provenance-observation.json": {
                    "source": "binance_demo_order_provenance_read_only",
                    "observed_at": now, "day_start_utc_ms": start,
                    "status": "AUDIT_ONLY_NOT_EXECUTABLE",
                    "total_fills": 5, "unique_orders": 4,
                    "verified_signalpilot_fills": 0,
                    "unattributed_fills": 5,
                    "order_classifications": {"EXTERNAL_OR_UNTAGGED": 4},
                    "allocation_ledger_reconciled": False,
                    "execution_authorized": False, "orders_sent": False},
                "demo-position-stress.json": {
                    "source": "binance_demo_position_stress_read_only",
                    "observed_at": now, "position_count": 0,
                    "unrealized_pnl_usdt": "0", "gross_notional_usdt": "0",
                    "stress_loss_2pct_usdt": "0", "stress_loss_5pct_usdt": "0",
                    "stress_2pct_exceeds_daily_cap": False,
                    "stress_5pct_exceeds_daily_cap": False,
                    "execution_authorized": False, "orders_sent": False},
                "demo-reconciliation-status.json": {
                    "source": "signalpilot_demo_reconciliation_guard_read_only",
                    "observed_at": now, "day_start_utc_ms": start,
                    "status": "BLOCKED_UNRECONCILED",
                    "unattributed_fills_today": 5,
                    "account_realized_gap_usdt": "-0.01",
                    "account_commission_gap_usdt": "0",
                    "account_funding_unattributed_usdt": "0",
                    "prior_day_exposure_unresolved": False,
                    "unattributed_history_unresolved": True,
                    "monitoring_gap_unresolved": False,
                    "open_exposure_now": False,
                    "allocation_ledger_reconciled": False,
                    "execution_authorized": False, "orders_sent": False},
                "demo-virtual-allocation.json": {
                    "source": "signalpilot_demo_virtual_allocation_read_only",
                    "observed_at": now, "day_start_utc_ms": start,
                    "status": "BLOCKED_OBSERVATION_ONLY",
                    "virtual_start_capital_usdt": "150",
                    "max_daily_loss_usdt": "7.50",
                    "unattributed_fills_today": 5,
                    "allocation_ledger_reconciled": False,
                    "execution_authorized": False, "orders_sent": False},
            }
            for name, obj in docs.items():
                (root / name).write_text(json.dumps(obj))
                (root / name).chmod(0o600)
            # Simulate root-owned observation fixtures on unprivileged CI runners.
            # Production ownership checks in demo_risk_monitor remain unchanged.
            original_lstat = Path.lstat
            trusted_names = {
                "demo-virtual-allocation.json", "demo-position-stress.json",
                "demo-reconciliation-status.json", "demo-provenance-observation.json"
            }
            def fixture_lstat(path, *args, **kwargs):
                stat = original_lstat(path, *args, **kwargs)
                if path.parent == root and path.name in trusted_names:
                    return SimpleNamespace(st_uid=0, st_mode=stat.st_mode)
                return stat
            ownership_patch = patch.object(Path, "lstat", fixture_lstat)
            ownership_patch.start()
            self.addCleanup(ownership_patch.stop)
            status = run(root)
            self.assertEqual(status["reason"], "UNATTRIBUTED_DEMO_FILLS")
            self.assertEqual(status["unattributed_fills"], 5)
            self.assertFalse(status["execution_authorized"])
            self.assertEqual(status["virtual_allocation_usdt"], "150")
            docs["demo-position-stress.json"]["stress_2pct_exceeds_daily_cap"] = True
            docs["demo-position-stress.json"]["stress_loss_2pct_usdt"] = "8"
            (root / "demo-position-stress.json").write_text(
                json.dumps(docs["demo-position-stress.json"]))
            status = run(root)
            self.assertEqual(status["reason"], "POSITION_STRESS_EXCEEDS_DAILY_CAP")
            self.assertFalse(status["execution_authorized"])
            docs["demo-position-stress.json"]["stress_2pct_exceeds_daily_cap"] = False
            docs["demo-position-stress.json"]["stress_loss_2pct_usdt"] = "0"
            (root / "demo-position-stress.json").write_text(
                json.dumps(docs["demo-position-stress.json"]))
            docs["demo-reconciliation-status.json"]["prior_day_exposure_unresolved"] = True
            (root / "demo-reconciliation-status.json").write_text(
                json.dumps(docs["demo-reconciliation-status.json"]))
            status = run(root)
            self.assertEqual(status["reason"], "PRIOR_DAY_EXPOSURE_UNRECONCILED")
            self.assertFalse(status["execution_authorized"])
            docs["demo-reconciliation-status.json"]["prior_day_exposure_unresolved"] = False
            (root / "demo-reconciliation-status.json").write_text(
                json.dumps(docs["demo-reconciliation-status.json"]))
            docs["demo-provenance-observation.json"]["unattributed_fills"] = 4
            (root / "demo-provenance-observation.json").write_text(
                json.dumps(docs["demo-provenance-observation.json"]))
            status = run(root)
            self.assertEqual(status["reason"], "MISSING_OR_INVALID_OBSERVATION")
            docs["demo-provenance-observation.json"]["unattributed_fills"] = 5
            (root / "demo-provenance-observation.json").write_text(
                json.dumps(docs["demo-provenance-observation.json"]))
            docs["demo-trade-attribution.json"]["observed_at"] = now - 100
            (root / "demo-trade-attribution.json").write_text(
                json.dumps(docs["demo-trade-attribution.json"]))
            status = run(root)
            self.assertEqual(status["reason"], "MISSING_OR_INVALID_OBSERVATION")


if __name__ == "__main__":
    unittest.main()
