import unittest
from signals_v2.contracts import Candle,DataRejected
from signals_v3.liquidity_reversal import liquidity_reversal

def bars(period,n):
    return tuple(Candle(i*period,100.,101.,99.,100.,10.,(i+1)*period) for i in range(n))

class ReversalTests(unittest.TestCase):
    def test_flat_market_no_reversal(self):
        self.assertEqual(liquidity_reversal("SOLUSDT",bars(300000,64),bars(60000,320),19200000),())
    def test_future_data_rejected(self):
        with self.assertRaisesRegex(DataRejected,"unavailable_or_unclosed_candle"):
            liquidity_reversal("SOLUSDT",bars(300000,64),bars(60000,320),19199999)
    def test_missing_bar_rejected(self):
        one=bars(60000,320)
        with self.assertRaisesRegex(DataRejected,"missing_or_duplicate_bar"):
            liquidity_reversal("SOLUSDT",bars(300000,64),one[:200]+one[201:],19200000)
    def test_sweep_low_reclaim_long(self):
        one=list(bars(60000,320));c=one[-1]
        one[-1]=Candle(c.open_ms,99.,100.5,98.,100.2,20.,c.available_at_ms)
        out=liquidity_reversal("SOLUSDT",bars(300000,64),tuple(one),19200000)
        self.assertEqual(len(out),1)
        self.assertEqual(out[0].direction,"LONG")
        self.assertFalse(out[0].execution_authorized)
    def test_sweep_high_reclaim_short(self):
        one=list(bars(60000,320));c=one[-1]
        one[-1]=Candle(c.open_ms,101.,102.,99.5,100.,20.,c.available_at_ms)
        out=liquidity_reversal("SOLUSDT",bars(300000,64),tuple(one),19200000)
        self.assertEqual(len(out),1)
        self.assertEqual(out[0].direction,"SHORT")
        self.assertFalse(out[0].execution_authorized)
if __name__=="__main__":unittest.main()
