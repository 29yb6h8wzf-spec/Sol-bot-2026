"""Offline read-only Binance Demo trade attribution tests."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from demo_trade_attribution import audit, fetch_day_trades, registry_orders

NOW = int(datetime(2026, 11, 3, 15, tzinfo=timezone.utc).timestamp() * 1000)
START = int(datetime(2026, 11, 3, tzinfo=timezone.utc).timestamp() * 1000)


def trade(order="123", client=None, *, fee="0.01", realized="0.5"):
    return {"symbol": "XRP/USDT:USDT", "id": "9001", "order": order,
            "timestamp": START + 2000,
            "fee": {"currency": "USDT", "cost": fee},
            "info": {"realizedPnl": realized}}


class Exchange:
    def __init__(self, *, trades=None, demo=True, order_client="SPDEMO-signal1"):
        self.urls = {"api": {"fapi": "https://demo-fapi.binance.com/fapi" if demo
                             else "https://fapi.binance.com/fapi"}}
        self.trades = [] if trades is None else trades
        self.order_client = order_client
        self.order_reads = 0
        self.trade_reads = 0

    def fetch_my_trades(self, symbol, since, limit):
        self.trade_reads += 1
        return self.trades if symbol == "XRP/USDT:USDT" else []

    def fetch_order(self, order_id, symbol):
        self.order_reads += 1
        return {"id": order_id, "symbol": symbol,
                "clientOrderId": self.order_client}


class AttributionTests(unittest.TestCase):
    def test_missing_registry_means_no_trusted_orders(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(registry_orders(Path(tmp) / "missing"), ({}, False))
            x = audit(Exchange(trades=[trade()]),
                      registry_path=Path(tmp) / "missing", now_ms=NOW)
            self.assertEqual(x["signalpilot_fills"], 0)
            self.assertEqual(x["unattributed_fills"], 1)
            self.assertFalse(x["allocation_ledger_reconciled"])

    @unittest.skipUnless(os.geteuid() == 0, "trusted registry requires root")
    def test_owned_order_requires_binance_client_id_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "registry.json"
            p.write_text(json.dumps({
                "schema_version": 1, "source": "signalpilot_demo_executor_registry",
                "execution_mode": "binance_demo",
                "orders": [{"symbol": "XRP/USDT:USDT", "order_id": "123",
                            "client_order_id": "SPDEMO-signal1",
                            "signal_id": "signal1"}]}))
            p.chmod(0o600)
            x = audit(Exchange(trades=[trade()]), registry_path=p, now_ms=NOW)
            self.assertEqual(x["signalpilot_fills"], 1)
            self.assertEqual(x["signalpilot_net_before_funding_usdt"], "0.49")
            self.assertFalse(x["execution_authorized"])
            with self.assertRaisesRegex(ValueError, "exchange_order_provenance_mismatch"):
                audit(Exchange(trades=[trade()], order_client="wrong"),
                      registry_path=p, now_ms=NOW)

    def test_live_endpoint_blocked_before_trades(self):
        e = Exchange(demo=False)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "non_demo_endpoint_blocked"):
                audit(e, registry_path=Path(tmp) / "missing", now_ms=NOW)
        self.assertEqual(e.trade_reads, 0)

    def test_missing_fee_blocks(self):
        t = trade()
        t["fee"] = None
        with self.assertRaisesRegex(ValueError, "unreconciled_trade_fee"):
            fetch_day_trades(Exchange(trades=[t]), now_ms=NOW)

    def test_missing_realized_pnl_blocks(self):
        t = trade()
        t["info"] = {}
        with self.assertRaisesRegex(ValueError, "missing_realized_pnl"):
            fetch_day_trades(Exchange(trades=[t]), now_ms=NOW)

    def test_untrusted_registry_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "registry.json"
            p.write_text("{}")
            p.chmod(0o644)
            with self.assertRaisesRegex(ValueError, "untrusted_registry_permissions"):
                registry_orders(p)

    def test_truncated_trade_page_fails_closed(self):
        e = Exchange(trades=[trade()])
        with self.assertRaisesRegex(ValueError, "incomplete_trade_history"):
            fetch_day_trades(e, now_ms=NOW, limit=1)

    def test_future_trade_rejected(self):
        t = trade()
        t["timestamp"] = NOW + 1000
        with self.assertRaisesRegex(ValueError, "invalid_trade_identity"):
            fetch_day_trades(Exchange(trades=[t]), now_ms=NOW)

if __name__ == "__main__":
    unittest.main()
