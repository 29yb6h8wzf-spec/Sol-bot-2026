"""Offline tests for historical kline pagination and fail-closed coverage."""
import unittest
from signals_v2.download_history import download


def candle(t):
    return [t, "10", "11", "9", "10.5", "100"]


class DownloadHistoryTests(unittest.TestCase):
    def test_complete_window(self):
        start = 1_800_000_000_000
        self.assertEqual(
            len(download("SOLUSDT", "1m", start, start + 180_000,
                         fetch=lambda url: [candle(start + i * 60_000) for i in range(3)])),
            3)

    def test_gap_fails_closed(self):
        start = 1_800_000_000_000
        with self.assertRaisesRegex(ValueError, "gap_duplicate"):
            download("XRPUSDT", "1m", start, start + 180_000,
                     fetch=lambda url: [candle(start), candle(start + 120_000)])

    def test_short_window_fails_closed(self):
        start = 1_800_000_000_000
        with self.assertRaisesRegex(ValueError, "short_history"):
            download("SOLUSDT", "1m", start, start + 180_000,
                     fetch=lambda url: [candle(start)])

    def test_invalid_symbol(self):
        with self.assertRaisesRegex(ValueError, "unsupported_market"):
            download("BTCUSDT", "1m", 0, 60_000, fetch=lambda url: [])

    def test_invalid_ohlc(self):
        start = 1_800_000_000_000
        with self.assertRaisesRegex(ValueError, "invalid_ohlcv"):
            download("SOLUSDT", "1m", start, start + 60_000,
                     fetch=lambda url: [[start, "10", "9", "11", "10", "100"]])


if __name__ == "__main__":
    unittest.main()
