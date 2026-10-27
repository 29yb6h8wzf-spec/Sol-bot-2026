import contextlib
import importlib
import io
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch

from futures_engine.core import Config, plan_trade
from futures_engine.paper import PaperLedger, locked_ledger
from futures_engine.market import closed_futures_bars, MarketDataError

STEP = 900000
MIDNIGHT = 1793145600000  # 2026-10-28 UTC


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'paper.json'
        self.ledger = PaperLedger(self.path)

    def enter(self, side='long', timestamp=MIDNIGHT):
        self.ledger.roll_day(timestamp)
        self.ledger.open_position(plan_trade(Config(), side, 100, 1000, 1000), timestamp)

    def exit(self, bars):
        return self.ledger.evaluate_exit(bars, D('.0006'), D('.0005'))

    def test_long_stop_gap_uses_worse_open(self):
        self.enter()
        event = self.exit([[MIDNIGHT+STEP, 90, 95, 89, 91, 1]])
        self.assertEqual(D(event['exit']), D(90))
        self.assertLess(D(event['pnl']), -D(10))

    def test_short_stop_gap_uses_worse_open(self):
        self.enter('short')
        event = self.exit([[MIDNIGHT+STEP, 110, 111, 108, 109, 1]])
        self.assertEqual(D(event['exit']), D(110))
        self.assertLess(D(event['pnl']), -D(10))

    def test_open_at_target_precedes_later_stop_touch(self):
        for side, opening, high, low, expected in [('long',105,106,97,104),('short',95,103,94,96)]:
            self.ledger = PaperLedger(Path(self.tmp.name) / (side+'.json'))
            self.enter(side)
            event = self.exit([[MIDNIGHT+STEP,opening,high,low,100,1]])
            self.assertEqual(event['reason'], 'target')
            self.assertEqual(D(event['exit']), D(expected))

    def test_old_exit_accounted_before_new_day(self):
        self.enter(timestamp=MIDNIGHT-3*STEP)
        event = self.exit([[MIDNIGHT-2*STEP,100,101,97,99,1],
                           [MIDNIGHT-STEP,99,100,98,99,1],
                           [MIDNIGHT,99,100,98,99,1]])
        self.assertEqual(event['timestamp'], MIDNIGHT-2*STEP)
        self.ledger.roll_day(MIDNIGHT)
        self.assertEqual(self.ledger.state['day_start_equity'], self.ledger.state['equity'])

    def test_midnight_exit_counts_against_new_day(self):
        self.enter(timestamp=MIDNIGHT-STEP)
        self.exit([[MIDNIGHT,100,101,97,99,1]])
        self.assertEqual(self.ledger.state['day_start_equity'], '1000')
        self.assertLess(D(self.ledger.state['equity']), D(1000))

    def test_missing_history_fails_without_writing(self):
        self.enter()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.exit([[MIDNIGHT+2*STEP,100,101,97,99,1]])
        self.assertEqual(self.path.read_bytes(), before)

    def test_cursor_survives_restart_and_repeated_bars(self):
        self.enter()
        bars = [[MIDNIGHT+STEP,100,101,99,100,1]]
        self.assertIsNone(self.exit(bars))
        self.ledger = PaperLedger(self.path)
        self.assertIsNone(self.exit(bars))
        event = self.exit([[MIDNIGHT+2*STEP,100,101,97,99,1]])
        self.assertEqual(event['reason'], 'stop')
        self.assertIsNone(self.exit(bars))
        self.assertEqual(len(self.ledger.state['history']), 2)

    def test_cost_model_is_frozen_at_entry(self):
        self.enter()
        event = self.ledger.evaluate_exit([[MIDNIGHT+STEP,100,101,97,99,1]], D(0), D(0))
        self.assertGreater(D(event['costs']), D(0))

    def test_market_identity_and_legacy_history_rejected(self):
        self.ledger.bind('BTC/USDT:USDT','15m',STEP)
        with self.assertRaisesRegex(ValueError, 'different market'):
            self.ledger.bind('SOL/USDT:USDT','15m',STEP)
        with self.assertRaisesRegex(ValueError, 'different market'):
            self.ledger.bind('BTC/USDT:USDT','1h',4*STEP)
        self.ledger.state.pop('market')
        self.enter()
        with self.assertRaisesRegex(ValueError, 'legacy'):
            self.ledger.bind('BTC/USDT:USDT','15m',STEP)

    def test_process_lock_and_release_on_exception(self):
        code = '''import sys
from decimal import Decimal
from futures_engine.paper import locked_ledger
try:
    with locked_ledger(sys.argv[1], Decimal(1000), 'BTC', '15m', 900000): pass
except ValueError as exc:
    assert 'locked' in str(exc)
    sys.exit(7)
'''
        with self.assertRaisesRegex(RuntimeError, 'simulated'):
            with locked_ledger(self.path, D(1000), 'BTC','15m',STEP):
                child = subprocess.run([sys.executable,'-c',code,str(self.path)], capture_output=True)
                self.assertEqual(child.returncode,7,child.stderr.decode())
                raise RuntimeError('simulated interruption')
        with locked_ledger(self.path,D(1000),'BTC','15m',STEP):
            pass

    def test_atomic_write_failure_preserves_previous_file(self):
        self.enter()
        before = self.path.read_bytes()
        with patch('futures_engine.paper.os.replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                self.ledger.save()
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(list(self.path.parent.glob('*.tmp')),[])

    def test_invalid_equity_and_backward_days(self):
        for value in ('NaN','Infinity','0','-1'):
            with self.assertRaises(ValueError):
                PaperLedger(self.path,D(value))
        self.ledger.roll_day(MIDNIGHT)
        with self.assertRaisesRegex(ValueError,'backwards'):
            self.ledger.roll_day(MIDNIGHT-STEP)


class RiskHardeningTests(unittest.TestCase):
    def test_remaining_daily_budget(self):
        for side in ('long','short'):
            plan = plan_trade(Config(),side,100,951,1000)
            self.assertLessEqual(D(plan['max_estimated_loss']),D(1))

    def test_nonfinite_config_and_inputs(self):
        for value in ('NaN','Infinity','-Infinity'):
            for key in ('risk_fraction','daily_loss_fraction','stop_fraction','reward_multiple','taker_fee','slippage_fraction'):
                with self.subTest(value=value,key=key), self.assertRaises(ValueError):
                    Config(**{key:D(value)}).validate()
            with self.assertRaises(ValueError):
                plan_trade(Config(),'long',D(value),1000,1000)
        with self.assertRaises(ValueError):
            Config(reward_multiple=D(50)).validate()


class FakeExchange:
    timeframes = {'15m': '15m'}
    def __init__(self):
        self.rows = [[i*STEP,100,101,99,100,1] for i in range(1001)]
        self.closed = False
        self.calls = 0
        self.failures = 0
    def load_markets(self):
        return {'BTC/USDT:USDT':{'swap':True,'linear':True,'settle':'USDT'}}
    def parse_timeframe(self, timeframe): return 900
    def milliseconds(self): return 1000*STEP
    def fetch_ohlcv(self,*args,**kwargs):
        self.calls += 1
        if self.calls <= self.failures: raise ConnectionError('temporary')
        return self.rows
    def close(self): self.closed = True


class MarketTests(unittest.TestCase):
    def fetch(self, exchange):
        ccxt = types.SimpleNamespace(binanceusdm=lambda options:exchange,
            RateLimitExceeded=ConnectionError, NetworkError=ConnectionError,
            RequestTimeout=ConnectionError,ExchangeNotAvailable=ConnectionError)
        with patch.dict(sys.modules,ccxt=ccxt), patch('futures_engine.market.time.sleep'):
            return closed_futures_bars('BTC/USDT:USDT','15m')

    def test_open_candle_excluded(self):
        exchange=FakeExchange()
        _,_,bars=self.fetch(exchange)
        self.assertEqual(len(bars),1000)
        self.assertEqual(bars[-1][0],999*STEP)

    def test_invalid_data_rejected_and_closed(self):
        mutations = [lambda rows:rows.__setitem__(30,[]),
                     lambda rows:rows[30].__setitem__(5,float('nan')),
                     lambda rows:rows[30].__setitem__(2,float('inf')),
                     lambda rows:rows[30].__setitem__(1,102),
                     lambda rows:rows.pop(30),
                     lambda rows:rows.__setitem__(30,rows[29]),
                     lambda rows:rows.__delitem__(slice(230,None))]
        for mutate in mutations:
            exchange=FakeExchange();mutate(exchange.rows)
            with self.subTest(mutate=mutate), self.assertRaises(MarketDataError):
                self.fetch(exchange)
            self.assertTrue(exchange.closed)

    def test_transient_retry_and_exhaustion(self):
        exchange=FakeExchange();exchange.failures=2
        self.fetch(exchange)
        self.assertEqual(exchange.calls,3)
        exchange=FakeExchange();exchange.failures=3
        with self.assertRaises(MarketDataError): self.fetch(exchange)
        self.assertEqual(exchange.calls,3)
        self.assertTrue(exchange.closed)


class CLITests(unittest.TestCase):
    def module(self):
        # dotenv is optional in these offline tests; no network dependency install.
        with patch.dict(sys.modules,dotenv=types.SimpleNamespace(load_dotenv=lambda:None)):
            return importlib.import_module('futures_engine.__main__')

    def test_live_mode_rejected_before_market_or_ledger_access(self):
        module=self.module()
        with patch.dict(os.environ,TRADING_MODE='live'), patch.object(module,'closed_futures_bars') as fetch:
            with self.assertRaisesRegex(SystemExit,'LIVE TRADING DISABLED'): module.main()
            fetch.assert_not_called()

    def test_scan_persists_and_replay_does_not_duplicate(self):
        module=self.module();exchange=FakeExchange()
        exchange.amount_to_precision=lambda symbol,quantity:str(D(quantity).quantize(D('.001'),rounding='ROUND_DOWN'))
        bars=exchange.rows[:-1]
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{'TRADING_MODE':'paper','PAPER_LEDGER':tmp+'/ledger.json','FUTURES_SYMBOL':'BTC/USDT:USDT','TIMEFRAME':'15m'}), patch.object(module,'closed_futures_bars',return_value=(exchange,{},bars)), patch.object(module,'advance_indicators',return_value={'signal':'long'}), contextlib.redirect_stdout(io.StringIO()):
            module.main();module.main()
            state=json.loads(Path(tmp+'/ledger.json').read_text())
            self.assertEqual(len(state['history']),1)
            self.assertLessEqual(D(state['position']['max_estimated_loss']),D(10))
            self.assertEqual(state['market']['symbol'],'BTC/USDT:USDT')
        self.assertTrue(exchange.closed)

    def test_real_indicator_state_survives_cli_restart(self):
        module=self.module();exchange=FakeExchange()
        from futures_engine.indicators import advance_indicators
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{'TRADING_MODE':'paper','PAPER_LEDGER':tmp+'/ledger.json','FUTURES_SYMBOL':'BTC/USDT:USDT','TIMEFRAME':'15m'}), contextlib.redirect_stdout(io.StringIO()):
            with patch.object(module,'closed_futures_bars',return_value=(exchange,{},exchange.rows[:1000])):
                module.main()
            with patch.object(module,'closed_futures_bars',return_value=(exchange,{},exchange.rows[1:])):
                module.main()
            state=json.loads(Path(tmp+'/ledger.json').read_text())
            self.assertEqual(state['indicators'],advance_indicators(None,exchange.rows,900000))
            self.assertEqual(state['indicators']['origin'],0)
