"""Persistent paper ledger. No live broker or create_order capability."""
import json
import os
from decimal import Decimal as D
from pathlib import Path
from .core import utc_day


class PaperLedger:
    def __init__(self, path, initial_equity=D('1000')):
        self.path = Path(path)
        if self.path.exists():
            self.state = json.loads(self.path.read_text())
        else:
            self.state = {'equity':str(initial_equity),'day':None,'day_start_equity':str(initial_equity),
                          'position':None,'last_signal_candle':None,'history':[]}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.state, indent=2))
        os.replace(temp, self.path)

    def roll_day(self, timestamp):
        day = utc_day(timestamp)
        if self.state['day'] != day:
            self.state['day'] = day
            self.state['day_start_equity'] = self.state['equity']
            self.save()

    def evaluate_exit(self, bars, fee_rate, slippage_rate, max_holding_minutes=None, timeframe_minutes=15):
        position = self.state['position']
        if not position:
            return None
        fee_rate, slippage_rate = D(str(fee_rate)), D(str(slippage_rate))
        if not all(x.is_finite() and x >= 0 for x in (fee_rate, slippage_rate)):
            raise ValueError('invalid paper execution costs')
        entry_ts = position['signal_candle']
        direction = D(1) if position['side'] == 'long' else D(-1)
        stop, target = D(position['stop']), D(position['target'])
        for bar in bars:
            if bar[0] <= entry_ts:
                continue
            if len(bar) < 6:
                raise ValueError('invalid paper candle')
            values = [D(str(x)) for x in bar[1:6]]
            op, high, low, close, volume = values
            if (not all(x.is_finite() for x in values) or
                min(op, high, low, close) <= 0 or volume < 0 or
                not low <= min(op, close) <= max(op, close) <= high):
                raise ValueError('invalid paper candle')
            hit_stop = low <= stop if direction > 0 else high >= stop
            hit_target = high >= target if direction > 0 else low <= target
            # Entry is at the signal candle close; exits use later closed candles.
            timed_out = (max_holding_minutes is not None and
                         bar[0] - entry_ts >= max_holding_minutes * 60000)
            if not (hit_stop or hit_target or timed_out):
                continue
            exit_price = stop if hit_stop else target if hit_target else close
            quantity, entry = D(position['quantity']), D(position['entry'])
            pnl = (exit_price - entry) * direction * quantity
            costs = (entry + exit_price) * quantity * (fee_rate + slippage_rate)
            pnl -= costs
            self.state['equity'] = str(D(self.state['equity']) + pnl)
            event = {'event':'paper_exit','side':position['side'],'exit':str(exit_price),
                     'reason':'stop' if hit_stop else 'target' if hit_target else 'time','pnl':str(pnl),'timestamp':bar[0]}
            self.state['history'].append(event)
            self.state['position'] = None
            self.save()
            return event
        return None

    def open_position(self, plan, signal_candle):
        # Fail closed before touching the persistent paper ledger.
        if not isinstance(plan, dict) or plan.get('side') not in ('long', 'short'):
            raise ValueError('invalid paper entry side')
        if type(signal_candle) is not int or signal_candle < 0:
            raise ValueError('invalid paper signal candle')
        try:
            entry, stop, target, qty = (D(str(plan[k])) for k in
                                        ('entry', 'stop', 'target', 'quantity'))
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise ValueError('invalid paper entry plan') from exc
        if not all(x.is_finite() and x > 0 for x in (entry, stop, target, qty)):
            raise ValueError('invalid paper entry numbers')
        if not (stop < entry < target if plan['side'] == 'long'
                else target < entry < stop):
            raise ValueError('invalid paper entry stop or target')
        if self.state['position'] or self.state['last_signal_candle'] == signal_candle:
            raise ValueError('position already open or duplicate signal')
        self.state['position'] = {**plan,'signal_candle':signal_candle}
        self.state['last_signal_candle'] = signal_candle
        self.state['history'].append({'event':'paper_entry',**self.state['position']})
        self.save()
