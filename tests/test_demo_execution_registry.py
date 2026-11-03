"""Offline tests for Binance DEMO order receipt registry. Never places orders."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from demo_execution_registry import client_order_id, record_confirmed_order
from demo_trade_attribution import registry_orders


class Exchange:
    def __init__(self, *, demo=True, expected=None):
        self.urls = {"api": {"fapi": "https://demo-fapi.binance.com/fapi"
                             if demo else "https://fapi.binance.com/fapi"}}
        self.expected = expected
        self.reads = 0

    def fetch_order(self, order_id, symbol):
        self.reads += 1
        return {"id": order_id, "symbol": symbol,
                "clientOrderId": self.expected}


class ReceiptRegistryTests(unittest.TestCase):
    def test_client_ids_are_deterministic_and_leg_specific(self):
        self.assertEqual(client_order_id("signal-1"), client_order_id("signal-1"))
        self.assertNotEqual(client_order_id("signal-1", "entry"),
                            client_order_id("signal-1", "stop"))
        self.assertLessEqual(len(client_order_id("signal-1")), 36)

    def test_reject_invalid_signal_id(self):
        with self.assertRaisesRegex(ValueError, "invalid_signal_id"):
            client_order_id("bad signal")

    def test_reject_invalid_leg(self):
        with self.assertRaisesRegex(ValueError, "invalid_order_leg"):
            client_order_id("signal-1", "unknown")

    def test_live_endpoint_never_fetches(self):
        ex = Exchange(demo=False)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "non_demo_endpoint_blocked"):
                record_confirmed_order(ex, signal_id="signal-1", leg="entry",
                    symbol="XRP/USDT:USDT", order_id="123",
                    registry_path=Path(tmp) / "registry.json")
        self.assertEqual(ex.reads, 0)

    def test_mismatched_exchange_order_never_writes(self):
        ex = Exchange(expected="wrong-client-id")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            with self.assertRaisesRegex(ValueError, "exchange_order_provenance_mismatch"):
                record_confirmed_order(ex, signal_id="signal-1", leg="entry",
                    symbol="XRP/USDT:USDT", order_id="123", registry_path=path)
            self.assertFalse(path.exists())

    @unittest.skipUnless(os.geteuid() == 0, "root-owned registry required")
    def test_confirmed_order_written_once(self):
        ex = Exchange(expected=client_order_id("signal-1", "entry"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            kwargs = dict(signal_id="signal-1", leg="entry",
                          symbol="XRP/USDT:USDT", order_id="123",
                          registry_path=path)
            self.assertEqual(record_confirmed_order(ex, **kwargs),
                             "RECORDED_VERIFIED_RECEIPT")
            self.assertEqual(record_confirmed_order(ex, **kwargs),
                             "ALREADY_RECORDED")
            orders, present = registry_orders(path)
            self.assertTrue(present)
            self.assertEqual(len(orders), 1)
            self.assertEqual(path.stat().st_mode & 0o077, 0)
            self.assertEqual(json.loads(path.read_text())["orders"][0]["signal_id"],
                             "signal-1")

    @unittest.skipUnless(os.geteuid() == 0, "root-owned registry required")
    def test_conflicting_receipt_rejected(self):
        ex = Exchange(expected=client_order_id("signal-1", "entry"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            record_confirmed_order(ex, signal_id="signal-1", leg="entry",
                                   symbol="XRP/USDT:USDT", order_id="123",
                                   registry_path=path)
            with self.assertRaisesRegex(ValueError, "conflicting_client_order_id"):
                record_confirmed_order(ex, signal_id="signal-1", leg="entry",
                                       symbol="XRP/USDT:USDT", order_id="124",
                                       registry_path=path)

if __name__ == "__main__":
    unittest.main()
