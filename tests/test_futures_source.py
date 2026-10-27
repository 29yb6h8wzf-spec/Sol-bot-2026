"""Regression tests: GitHub research scans must never use Spot market candles."""
import contextlib
import io
import json
import unittest
from unittest import mock

import bot


class KrakenSourceTests(unittest.TestCase):
    def test_source_is_public_kraken_spot(self):
        self.assertEqual(bot.BASE, 'https://api.kraken.com/0/public/OHLC')
        self.assertIn('Kraken Spot', bot.DATA_SOURCE)
        self.assertNotIn('/api/v3/', bot.BASE)

    def test_kraken_public_ohlc_excludes_open_candle(self):
        import time
        end = int(time.time()) // 300 * 300
        rows = [[end - 900, '100', '101', '99', '100.5', '100', '200', 1],
                [end - 600, '100', '101', '99', '100.5', '100', '201', 1],
                [end - 300, '100', '101', '99', '100.5', '100', '202', 1],
                [end, '100', '101', '99', '100.5', '100', '203', 1]]
        called = []
        def fake_urlopen(url, timeout):
            called.append(url)
            return io.BytesIO(json.dumps({'error': [], 'result': {'TEST': rows, 'last': end}}).encode())
        with mock.patch.object(bot.urllib.request, 'urlopen', side_effect=fake_urlopen):
            bars = bot.fetch('5m', 3)
        self.assertEqual(len(bars), 3)
        self.assertEqual(bars[-1]['volume'], 202.0)
        self.assertEqual(bars[-1]['time'], (end - 300) * 1000)
        self.assertIn('interval=5', called[0])

    def test_kraken_error_fails_closed(self):
        def fake_urlopen(url, timeout):
            return io.BytesIO(json.dumps({'error': ['EQuery:Unknown asset pair']}).encode())
        with mock.patch.object(bot.urllib.request, 'urlopen', side_effect=fake_urlopen):
            with self.assertRaises(ValueError):
                bot.fetch('5m', 3)

    def test_pair_uses_only_kraken(self):
        with mock.patch.object(bot, 'fetch', side_effect=lambda interval, limit: [interval]) as fetch:
            with contextlib.redirect_stdout(io.StringIO()):
                four, five = bot.fetch_pair(120)
        self.assertEqual((four, five), (['4h'], ['5m']))
        self.assertEqual(fetch.call_count, 2)

    def test_diagnostic_logs_identify_spot_source(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            bot.scan_log('test')
        line = output.getvalue().split('SCAN_EVENT ', 1)[1]
        self.assertEqual(json.loads(line)['source'], bot.DATA_SOURCE)




if __name__ == '__main__':
    unittest.main()
