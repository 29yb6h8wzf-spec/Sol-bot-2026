"""Offline tests for read-only demo exposure observation."""
import unittest
from demo_exposure_observer import observe

class Exchange:
    def __init__(self, demo=True, positions=None):
        self.urls = {"api": {"fapi": "https://demo-fapi.binance.com/fapi" if demo
                             else "https://fapi.binance.com/fapi"}}
        self.positions = [] if positions is None else positions
        self.calls = 0
    def fetch_positions(self):
        self.calls += 1
        return self.positions

class ExposureTests(unittest.TestCase):
    def test_empty(self):
        x = observe(Exchange(), now=100)
        self.assertEqual(x["unrealized_pnl_usdt"], "0")
        self.assertEqual(x["exposed_symbols"], [])
        self.assertFalse(x["execution_authorized"])

    def test_open_unrealized_loss(self):
        x = observe(Exchange(positions=[{
            "symbol": "XRP/USDT:USDT", "contracts": 10, "unrealizedPnl": "-2.5"}]), now=100)
        self.assertEqual(x["unrealized_pnl_usdt"], "-2.5")
        self.assertEqual(x["exposed_symbols"], ["XRP/USDT:USDT"])

    def test_missing_pnl_fails(self):
        with self.assertRaisesRegex(ValueError, "missing_unrealized_pnl"):
            observe(Exchange(positions=[{"symbol": "XRP/USDT:USDT", "contracts": 1}]))

    def test_live_endpoint_blocked(self):
        x = Exchange(demo=False)
        with self.assertRaisesRegex(RuntimeError, "non_demo_endpoint_blocked"):
            observe(x)
        self.assertEqual(x.calls, 0)

    def test_nonfinite_pnl_fails(self):
        with self.assertRaisesRegex(ValueError, "invalid_unrealized_pnl"):
            observe(Exchange(positions=[{
                "symbol": "XRP/USDT:USDT", "contracts": 1, "unrealizedPnl": "NaN"}]))

if __name__ == "__main__":
    unittest.main()
