"""Offline failure-injection tests for the demo cleanup. No network, keys or orders."""
import importlib.util
import pathlib
import unittest
from unittest.mock import patch

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "signalpilot_demo_bracket_test.py"
spec = importlib.util.spec_from_file_location("demo_bracket", SCRIPT)
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


class FakeExchange:
    def __init__(self, *, failures=0, remaining=1):
        self.remaining = remaining
        self.failures = failures
        self.actions = []
        self.urls = {"api": {"fapiPrivate": "https://demo-fapi.binance.com"}}

    def fetch_positions(self, symbols):
        return [{"symbol": demo.SYMBOL, "side": "long", "contracts": self.remaining}]

    def create_order(self, *args):
        self.actions.append("flatten")
        if self.failures:
            self.failures -= 1
            raise TimeoutError("injected network timeout")
        self.remaining = 0

    def market_id(self, symbol):
        return "XRPUSDT"

    def fapiPrivateDeleteAlgoOpenOrders(self, params):
        self.actions.append("cancel_algo")

    def cancel_all_orders(self, symbol):
        self.actions.append("cancel_basic")

    def fetch_open_orders(self, symbol):
        return []

    def fapiPrivateGetOpenAlgoOrders(self, params):
        return {"orders": []}


class CleanupTests(unittest.TestCase):
    @patch.object(demo.time, "sleep", return_value=None)
    def test_flatten_before_cancel(self, _):
        e = FakeExchange()
        demo.cleanup(e)
        self.assertEqual(e.actions, ["flatten", "cancel_algo", "cancel_basic"])

    @patch.object(demo.time, "sleep", return_value=None)
    def test_timeout_then_recovery(self, _):
        e = FakeExchange(failures=1)
        demo.cleanup(e)
        self.assertEqual(e.actions, ["flatten", "flatten", "cancel_algo", "cancel_basic"])

    @patch.object(demo.time, "sleep", return_value=None)
    def test_persistent_failure_keeps_protection(self, _):
        e = FakeExchange(failures=3)
        with self.assertRaisesRegex(RuntimeError, "protective orders NOT canceled"):
            demo.cleanup(e)
        self.assertEqual(e.actions, ["flatten", "flatten", "flatten"])

    @patch.object(demo.time, "sleep", return_value=None)
    def test_already_flat_cleanup(self, _):
        e = FakeExchange(remaining=0)
        demo.cleanup(e)
        self.assertEqual(e.actions, ["cancel_algo", "cancel_basic"])


if __name__ == "__main__":
    unittest.main()
