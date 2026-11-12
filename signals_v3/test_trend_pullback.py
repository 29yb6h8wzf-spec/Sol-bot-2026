import unittest
from dataclasses import replace
from signals_v2.contracts import Candle,DataRejected
from signals_v3.trend_pullback import trend_pullback

class TrendPullbackTests(unittest.TestCase):
    def bars(self,period,n,price=100):
        return tuple(Candle(i*period,price,price+1,price-1,price,10,(i+1)*period) for i in range(n))
    def test_flat_market_has_no_signal(self):
        five=self.bars(300000,64)
        one=self.bars(60000,320)
        self.assertEqual(trend_pullback("SOLUSDT",five,one,19200000),())
    def test_reject_future_candle(self):
        five=self.bars(300000,64)
        one=self.bars(60000,320)
        with self.assertRaisesRegex(DataRejected,"unavailable_or_unclosed_candle"):
            trend_pullback("SOLUSDT",five,one,19199999)
    def test_reject_missing_1m(self):
        five=self.bars(300000,64)
        one=self.bars(60000,320)
        one=one[:200]+one[201:]
        with self.assertRaisesRegex(DataRejected,"missing_or_duplicate_bar"):
            trend_pullback("SOLUSDT",five,one,19200000)
    def test_reject_insufficient_history(self):
        with self.assertRaisesRegex(DataRejected,"insufficient_v3_history"):
            trend_pullback("SOLUSDT",(),(),1)
if __name__=="__main__":unittest.main()
