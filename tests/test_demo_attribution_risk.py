"""Read-only risk monitor integration with trade attribution audit."""
import json
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
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
                    "unattributed_fills": 5,
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
            status = run(root)
            self.assertEqual(status["reason"], "UNATTRIBUTED_DEMO_FILLS")
            self.assertEqual(status["unattributed_fills"], 5)
            self.assertFalse(status["execution_authorized"])
            self.assertEqual(status["virtual_allocation_usdt"], "150")
            docs["demo-trade-attribution.json"]["observed_at"] = now - 100
            (root / "demo-trade-attribution.json").write_text(
                json.dumps(docs["demo-trade-attribution.json"]))
            status = run(root)
            self.assertEqual(status["reason"], "MISSING_OR_INVALID_OBSERVATION")


if __name__ == "__main__":
    unittest.main()
