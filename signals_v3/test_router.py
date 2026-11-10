import unittest
from signals_v2.contracts import Candle,DataRejected
from signals_v3.router import candidates

def bars(period,n):
    return tuple(Candle(i*period,100.,101.,99.,100.,10.,(i+1)*period) for i in range(n))

class RouterTests(unittest.TestCase):
    def test_flat_market_no_candidates(self):
        self.assertEqual(candidates("SOLUSDT",bars(300000,64),bars(60000,320),19200000),())
    def test_dynamic_universe_not_implicitly_approved(self):
        with self.assertRaisesRegex(DataRejected,"dynamic_universe_not_yet_verified"):
            candidates("DOGEUSDT",bars(300000,64),bars(60000,320),19200000)
if __name__=="__main__":unittest.main()
