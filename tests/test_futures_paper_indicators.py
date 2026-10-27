import json
import math
import unittest
from decimal import Decimal as D
from futures_engine.core import ema, rsi, crossover_signal
from futures_engine.indicators import advance_indicators

STEP=900000

class IndicatorTests(unittest.TestCase):
    def setUp(self):
        self.bars=[[i*STEP,100,120,80,100+8*math.sin(i/80)+3*math.sin(i/11),1] for i in range(1100)]

    def test_continuous_and_json_restart_match_batch_and_reference(self):
        state=advance_indicators(None,self.bars[:1000],STEP)
        for end in range(1001,len(self.bars)+1):
            # Real scans have a moving window, but never reseed indicators.
            state=advance_indicators(json.loads(json.dumps(state)),self.bars[end-239:end],STEP)
            prices=[D(str(b[4])) for b in self.bars[:end]]
            self.assertEqual(D(state['fast']),ema(prices,50))
            self.assertEqual(D(state['slow']),ema(prices,200))
            gain,loss=D(state['gain']),D(state['loss'])
            momentum=(D(100) if gain else D(50)) if loss==0 else D(100)-D(100)/(1+gain/loss)
            self.assertEqual(momentum,rsi(prices))
            self.assertEqual(state['signal'],crossover_signal(self.bars[:end]))
        self.assertEqual(state,advance_indicators(None,self.bars,STEP))

    def test_same_scan_is_idempotent(self):
        state=advance_indicators(None,self.bars[:1000],STEP)
        self.assertEqual(state,advance_indicators(state,self.bars[761:1000],STEP))

    def test_gap_failure_does_not_mutate_state(self):
        state=advance_indicators(None,self.bars[:1000],STEP)
        before=json.dumps(state)
        with self.assertRaisesRegex(ValueError,'missing'):
            advance_indicators(state,self.bars[1001:],STEP)
        self.assertEqual(before,json.dumps(state))

    def test_warmup_revision_and_corrupt_state_fail_closed(self):
        with self.assertRaisesRegex(ValueError,'1000'):
            advance_indicators(None,self.bars[:999],STEP)
        state=advance_indicators(None,self.bars[:1000],STEP)
        revised=[list(b) for b in self.bars[999:]];revised[0][4]+=1
        with self.assertRaisesRegex(ValueError,'revised'):
            advance_indicators(state,revised,STEP)
        for key,value in [('slow','NaN'),('version',2),('duration',1)]:
            bad={**state,key:value}
            with self.assertRaises(ValueError):advance_indicators(bad,self.bars,STEP)

    def test_constant_prices_have_neutral_rsi_and_no_signal(self):
        bars=[[i*STEP,100,100,100,100,1] for i in range(1001)]
        state=advance_indicators(None,bars,STEP)
        self.assertEqual(D(state['gain']),0)
        self.assertEqual(D(state['loss']),0)
        self.assertIsNone(state['signal'])
