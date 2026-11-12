import unittest
from unittest.mock import patch
from signals_v3.capture_full_current_universe import capture_full_current_universe


class FullUniverseCaptureTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.markets = {"symbols": [
            {"symbol": f"T{i}USDT", "quoteAsset": "USDT", "contractType": "PERPETUAL",
             "status": "TRADING", "filters": [{"filterType": "MIN_NOTIONAL", "notional": "5"}]}
            for i in range(25)
        ]}
        self.prices = [{"symbol": f"T{i}USDT", "price": "2"} for i in range(25)]

    def fetch(self, path, params=None):
        self.calls.append((path, params))
        if path == "/fapi/v1/exchangeInfo":
            return self.markets
        if path == "/fapi/v1/ticker/price":
            return self.prices
        if path == "/fapi/v1/ticker/24hr":
            return {"lastPrice": "2", "quoteVolume": "20000000"}
        if path == "/fapi/v1/depth":
            return {"bids": [["1.999", "10000"]], "asks": [["2.001", "10000"]]}
        raise AssertionError(path)

    def test_captures_all_25_not_just_first_20(self):
        result = capture_full_current_universe(fetch=self.fetch, clock_ms=lambda: 1000)
        self.assertEqual(result["captured_count"], 25)
        self.assertTrue(result["complete_market_capture"])
        self.assertFalse(result["historical_universe_verified"])
        self.assertEqual(sum(path == "/fapi/v1/exchangeInfo" for path, _ in self.calls), 1)
        self.assertEqual(sum(path == "/fapi/v1/depth" for path, _ in self.calls), 25)

    def test_partial_depth_failure_cannot_be_complete(self):
        def failing(path, params=None):
            if path == "/fapi/v1/depth" and params["symbol"] == "T10USDT":
                raise RuntimeError("rate_limited")
            return self.fetch(path, params)
        with self.assertRaisesRegex(RuntimeError, "rate_limited"):
            capture_full_current_universe(fetch=failing, clock_ms=lambda: 1000)

    def test_future_dated_snapshot_rejected(self):
        with patch("signals_v3.capture_full_current_universe.discover_current_price_candidates", return_value=["T0USDT"]), \
             patch("signals_v3.capture_full_current_universe.snapshot_symbol",
                   return_value={"symbol": "T0USDT", "observed_at_ms": 2000}):
            with self.assertRaisesRegex(ValueError, "snapshot_timestamp_after_capture"):
                capture_full_current_universe(fetch=self.fetch, clock_ms=lambda: 1000)

    def test_non_monotonic_snapshot_timestamps_rejected(self):
        snapshots = [
            {"symbol": "T0USDT", "observed_at_ms": 1500},
            {"symbol": "T1USDT", "observed_at_ms": 1200},
        ]
        with patch("signals_v3.capture_full_current_universe.discover_current_price_candidates",
                   return_value=["T0USDT", "T1USDT"]), \
             patch("signals_v3.capture_full_current_universe.snapshot_symbol",
                   side_effect=snapshots):
            with self.assertRaisesRegex(ValueError, "non_monotonic_market_snapshot"):
                capture_full_current_universe(fetch=self.fetch, clock_ms=lambda: 1000)

    def test_slow_capture_fails_closed(self):
        times = iter([0] + [1000] * 50 + [400000] * 50)
        with self.assertRaisesRegex(ValueError, "complete_capture_too_slow"):
            capture_full_current_universe(fetch=self.fetch, clock_ms=lambda: next(times))


if __name__ == "__main__":
    unittest.main()
