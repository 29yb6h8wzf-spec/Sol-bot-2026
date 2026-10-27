"""Regression tests: GitHub research scans must never use Spot market candles."""
import contextlib
import io
import json
import unittest
from unittest import mock

import bot


class FuturesSourceTests(unittest.TestCase):
    def test_source_is_binance_usdm_perpetual(self):
        self.assertEqual(bot.BASE, 'https://fapi.binance.com/fapi/v1/klines')
        self.assertIn('Perpetual', bot.DATA_SOURCE)
        self.assertNotIn('/api/v3/', bot.BASE)

    def test_fetch_uses_only_futures_and_excludes_open_candle(self):
        rows = [[i * 300000, '100', '101', '99', '100.5', '200', i * 300000 + 299999]
                for i in range(3)]
        called = []

        def fake_urlopen(url, timeout):
            called.append(url)
            return io.BytesIO(json.dumps(rows).encode('utf-8'))

        with mock.patch.object(bot.urllib.request, 'urlopen', side_effect=fake_urlopen):
            candles = bot.fetch('5m', 3)
        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0]['volume'], 200.0)
        self.assertEqual(len(called), 1)
        self.assertTrue(called[0].startswith(bot.BASE + '?'))
        self.assertIn('symbol=SOLUSDT', called[0])
        self.assertIn('interval=5m', called[0])

    def test_futures_outage_fails_closed_without_spot_fallback(self):
        called = []

        def unavailable(url, timeout):
            called.append(url)
            raise OSError('Futures unavailable')

        with mock.patch.object(bot.urllib.request, 'urlopen', side_effect=unavailable):
            with self.assertRaises(OSError):
                bot.fetch('5m', 3)
        self.assertEqual(len(called), 1)
        self.assertTrue(called[0].startswith(bot.BASE))

    def test_diagnostic_logs_identify_futures_source(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            bot.scan_log('test')
        line = output.getvalue().split('SCAN_EVENT ', 1)[1]
        self.assertEqual(json.loads(line)['source'], bot.DATA_SOURCE)


if __name__ == '__main__':
    unittest.main()
