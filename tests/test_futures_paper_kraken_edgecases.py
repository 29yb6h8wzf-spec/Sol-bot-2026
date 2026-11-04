"""Additional fail-closed edge cases for public Kraken spot candles."""
import sys
import types
import unittest
from unittest.mock import patch

from futures_engine.alternate_market_smoke import inspect

STEP = 300000
START = 1800000000000


class FakeExchange:
    def __init__(self, rows):
        self.rows = rows
        self.closed = False

    def load_markets(self):
        return {"BTC/USDT": {"spot": True, "active": True}}

    def parse_timeframe(self, timeframe):
        return 300

    def fetch_ohlcv(self, symbol, timeframe, limit):
        return self.rows

    def milliseconds(self):
        return START + 120 * STEP + 30000

    def close(self):
        self.closed = True


class MarketEdgeCases(unittest.TestCase):
    def check_rejected(self, mutate):
        rows = [[START + i * STEP, 100, 102, 99, 101, 1] for i in range(120)]
        mutate(rows)
        exchange = FakeExchange(rows)
        with patch.dict(sys.modules, {"ccxt": types.SimpleNamespace(kraken=lambda _: exchange)}):
            with self.assertRaises(ValueError):
                inspect("BTC/USDT")
        self.assertTrue(exchange.closed)

    def test_nan_close_rejected(self):
        self.check_rejected(lambda rows: rows[50].__setitem__(4, float("nan")))

    def test_infinite_volume_rejected(self):
        self.check_rejected(lambda rows: rows[50].__setitem__(5, float("inf")))

    def test_boolean_price_rejected(self):
        self.check_rejected(lambda rows: rows[50].__setitem__(4, True))

    def test_malformed_row_rejected(self):
        self.check_rejected(lambda rows: rows.__setitem__(50, [START + 50 * STEP, 100]))

    def test_negative_timestamp_rejected(self):
        self.check_rejected(lambda rows: rows[50].__setitem__(0, -STEP))


if __name__ == "__main__":
    unittest.main()
