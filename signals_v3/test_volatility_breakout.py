import unittest
from signals_v2.contracts import Candle,DataRejected
from signals_v3.volatility_breakout import volatility_breakout

def bars(period,n):
    return tuple(Candle(i*period,100.,101.,99.,100.,10.,(i+1)*period) for i in range(n))

class BreakoutTests(unittest.TestCase):
    def test_flat_market_no_breakout(self):
        self.assertEqual(volatility_breakout("SOLUSDT",bars(300000,64),bars(60000,320),19200000),())
    def test_future_data_rejected(self):
        with self.assertRaisesRegex(DataRejected,"unavailable_or_unclosed_candle"):
            volatility_breakout("SOLUSDT",bars(300000,64),bars(60000,320),19199999)
    def test_missing_bar_rejected(self):
        one=bars(60000,320)
        with self.assertRaisesRegex(DataRejected,"missing_or_duplicate_bar"):
            volatility_breakout("SOLUSDT",bars(300000,64),one[:200]+one[201:],19200000)
    def test_insufficient_history_rejected(self):
        with self.assertRaisesRegex(DataRejected,"insufficient_v3_history"):
            volatility_breakout("SOLUSDT",(),(),1)
    def test_breakout_detected(self):
        five=bars(300000,64)
        one=list(bars(60000,320))
        # Older 20-bar range wider than recent compression.
        for i in range(279,299):
            c=one[i];one[i]=Candle(c.open_ms,100.,103.,97.,100.,10.,c.available_at_ms)
        for i in range(299,319):
            c=one[i];one[i]=Candle(c.open_ms,100.,100.5,99.5,100.,10.,c.available_at_ms)
        c=one[319];one[319]=Candle(c.open_ms,100.,102.,100.,102.,20.,c.available_at_ms)
        result=volatility_breakout("SOLUSDT",five,tuple(one),19200000)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0].direction,"LONG")
        self.assertFalse(result[0].execution_authorized)
if __name__=="__main__":unittest.main()
