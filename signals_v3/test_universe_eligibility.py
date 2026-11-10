import unittest
from signals_v3.universe_eligibility import eligible_contract, UniverseRejected

CONTRACT = {"symbol": "LINKUSDT", "quoteAsset": "USDT", "contractType": "PERPETUAL", "status": "TRADING"}
TICKER = {"symbol": "LINKUSDT", "price": "12.50", "timestamp_ms": 100000}

class UniverseEligibilityTests(unittest.TestCase):
    def check(self, contract=None, ticker=None, decision_ms=100000):
        return eligible_contract(CONTRACT if contract is None else contract,
                                 TICKER if ticker is None else ticker, decision_ms)

    def test_inclusive_price_boundaries(self):
        for price in ("0.99", "150"):
            self.assertTrue(self.check(ticker={**TICKER, "price": price}))
        for price in ("0.989", "150.001"):
            self.assertFalse(self.check(ticker={**TICKER, "price": price}))

    def test_rejects_bad_prices(self):
        for price in (None, True, [], "NaN", "Infinity", "-1", "0", "abc"):
            with self.subTest(price=price), self.assertRaises(UniverseRejected):
                self.check(ticker={**TICKER, "price": price})

    def test_rejects_stale_future_and_bad_timestamps(self):
        for ts in (99999 - 300000, 100001, None, True, "100000"):
            with self.subTest(ts=ts), self.assertRaises(UniverseRejected):
                self.check(ticker={**TICKER, "timestamp_ms": ts})
        self.assertTrue(self.check(decision_ms=400000))

    def test_rejects_non_perpetual_or_inactive(self):
        for field, value in (("status", "BREAK"), ("contractType", "CURRENT_QUARTER"),
                             ("quoteAsset", "BUSD"), ("symbol", "LINKBUSD")):
            with self.subTest(field=field), self.assertRaises(UniverseRejected):
                self.check(contract={**CONTRACT, field: value})
        with self.assertRaises(UniverseRejected):
            self.check(ticker={**TICKER, "symbol": "XRPUSDT"})

    def test_rejects_invalid_decision_time(self):
        for time in (0, -1, True, 1.5):
            with self.assertRaises(UniverseRejected):
                self.check(decision_ms=time)

if __name__ == "__main__":
    unittest.main()
