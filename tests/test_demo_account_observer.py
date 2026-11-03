"""Offline account observer tests; no Binance connectivity."""
import tempfile
import unittest
from pathlib import Path

from demo_account_observer import assert_demo, observe, save_observation


class Exchange:
    def __init__(self, demo=True):
        self.urls = {"api": {"fapi": "https://demo-fapi.binance.com/fapi"
                             if demo else "https://fapi.binance.com/fapi"}}
    def load_markets(self):
        return {}
    def fetch_balance(self):
        return {"USDT": {"total": 150, "free": 149}}
    def fetch_positions(self):
        return [{"symbol": "XRP/USDT:USDT", "contracts": 0}]
    def fetch_open_orders(self, symbol):
        return []
    def market_id(self, symbol):
        return symbol.split("/")[0] + "USDT"
    def fapiPrivateGetOpenAlgoOrders(self, params):
        return []


class ObserverTests(unittest.TestCase):
    def test_demo_only(self):
        assert_demo(Exchange())
        with self.assertRaisesRegex(RuntimeError, "non_demo_endpoint_blocked"):
            observe(Exchange(demo=False))

    def test_read_only_summary(self):
        result = observe(Exchange())
        self.assertEqual(result["usdt_total"], "150")
        self.assertEqual(result["exposed_symbols"], [])
        self.assertFalse(result["risk_snapshot_approved"])
        self.assertFalse(result["orders_sent"])

    def test_open_exposure_is_visible(self):
        class Exposed(Exchange):
            def fetch_positions(self):
                return [{"symbol": "SOL/USDT:USDT", "contracts": 2}]
        self.assertEqual(observe(Exposed())["exposed_symbols"], ["SOL/USDT:USDT"])

    def test_missing_balance_fails(self):
        class Missing(Exchange):
            def fetch_balance(self):
                return {}
        with self.assertRaises(ValueError):
            observe(Missing())

    def test_atomic_private_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "observation.json"
            save_observation({"risk_snapshot_approved": False}, target)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
