"""Deterministic tests of public 5m historical pagination, no network."""
import io
import json
import unittest
from urllib.parse import parse_qs, urlparse

from futures_engine.research_fetch_public_5m import download


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def bar(t):
    return [t, "100", "101", "99", "100", "5"]


class PublicFiveMinuteDownloaderTests(unittest.TestCase):
    def test_two_pages_and_exact_utc_end(self):
        calls = []

        def opener(url, timeout):
            self.assertEqual(timeout, 20)
            params = parse_qs(urlparse(url).query)
            calls.append(params)
            start = int(params["startTime"][0])
            end = int(params["endTime"][0])
            size = min(1500, (end - start + 1) // 300000)
            return Response(json.dumps([bar(start + i * 300000)
                                        for i in range(size)]).encode())

        result = download("SOLUSDT", 0, 1501 * 300000, opener=opener)
        self.assertEqual(len(result), 1501)
        self.assertEqual(len(calls), 2)
        self.assertEqual(int(calls[1]["startTime"][0]), 1500 * 300000)
        self.assertEqual(result[-1][0], 1500 * 300000)

    def test_gap_rejected(self):
        def opener(url, timeout):
            return Response(json.dumps([bar(0), bar(600000)]).encode())
        with self.assertRaisesRegex(ValueError, "market_history_gap_or_duplicate"):
            download("XRPUSDT", 0, 900000, opener=opener)

    def test_empty_page_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing_market_history"):
            download("SOLUSDT", 0, 300000,
                     opener=lambda url, timeout: Response(b"[]"))

    def test_symbol_and_utc_alignment_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported_symbol"):
            download("BTCUSDT", 0, 300000)
        with self.assertRaisesRegex(ValueError, "invalid_utc_range"):
            download("SOLUSDT", 1, 300000)

    def test_unclosed_candle_rejected(self):
        with self.assertRaisesRegex(ValueError, "unclosed_market_candle"):
            download("SOLUSDT", 0, 300000,
                     opener=lambda url, timeout:
                     Response(json.dumps([bar(300000)]).encode()))


if __name__ == "__main__":
    unittest.main()
