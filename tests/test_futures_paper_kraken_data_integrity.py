"""Offline tests of the real Kraken spot OHLCV validation path."""
import sys
import types
import unittest
from unittest.mock import patch

from futures_engine.alternate_market_smoke import inspect


DURATION = 300_000
START = 1_800_000_000_000


class FakeExchange:
    def __init__(self, rows, *, market=None, now=None):
        self.rows = rows
        self.market = market or {"spot": True, "active": True}
        self.now = now if now is not None else rows[-1][0] + DURATION + 30_000
        self.closed = False

    def load_markets(self):
        return {"BTC/USDT": self.market}

    def parse_timeframe(self, timeframe):
        assert timeframe == "5m"
        return 300

    def fetch_ohlcv(self, symbol, timeframe, limit):
        assert symbol == "BTC/USDT"
        assert limit == 240
        return self.rows

    def milliseconds(self):
        return self.now

    def close(self):
        self.closed = True


def candles():
    return [[START + i * DURATION, 100, 102, 99, 101, 2] for i in range(120)]


class KrakenDataIntegrityTests(unittest.TestCase):
    def run_check(self, exchange):
        with patch.dict(sys.modules, {"ccxt": types.SimpleNamespace(kraken=lambda _: exchange)}):
            return inspect("BTC/USDT")

    def test_valid_closed_contiguous_spot_bars(self):
        exchange = FakeExchange(candles())
        result = self.run_check(exchange)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["closed_candles"], 120)
        self.assertTrue(exchange.closed)

    def test_gap_fails_closed(self):
        rows = candles()
        rows[70][0] += DURATION
        exchange = FakeExchange(rows)
        with self.assertRaisesRegex(ValueError, "gapped"):
            self.run_check(exchange)
        self.assertTrue(exchange.closed)

    def test_stale_fails_closed(self):
        rows = candles()
        exchange = FakeExchange(rows, now=rows[-1][0] + 4 * DURATION)
        with self.assertRaisesRegex(ValueError, "stale"):
            self.run_check(exchange)
        self.assertTrue(exchange.closed)

    def test_bad_ohlc_fails_closed(self):
        rows = candles()
        rows[12][4] = 110
        exchange = FakeExchange(rows)
        with self.assertRaisesRegex(ValueError, "invalid"):
            self.run_check(exchange)
        self.assertTrue(exchange.closed)

    def test_non_spot_market_rejected(self):
        exchange = FakeExchange(candles(), market={"spot": False, "active": True})
        with self.assertRaisesRegex(ValueError, "spot market unavailable"):
            self.run_check(exchange)
        self.assertTrue(exchange.closed)

    def test_too_few_closed_candles_rejected(self):
        exchange = FakeExchange(candles()[:50])
        with self.assertRaisesRegex(ValueError, "insufficient"):
            self.run_check(exchange)
        self.assertTrue(exchange.closed)


if __name__ == "__main__":
    unittest.main()
