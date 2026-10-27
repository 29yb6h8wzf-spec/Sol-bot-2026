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

    def evaluate_exit(self, bars, fee_rate, slippage_rate):
        position = self.state['position']
        if not position:
            return None
        entry_ts = position['signal_candle']
        direction = D(1) if position['side'] == 'long' else D(-1)
        stop, target = D(position['stop']), D(position['target'])
        for bar in bars:
            if bar[0] <= entry_ts:
                continue
            hit_stop = bar[3] <= stop if direction > 0 else bar[2] >= stop
            hit_target = bar[2] >= target if direction > 0 else bar[3] <= target
            if not (hit_stop or hit_target):
                continue
            exit_price = stop if hit_stop else target
            quantity, entry = D(position['quantity']), D(position['entry'])
            pnl = (exit_price - entry) * direction * quantity
            costs = (entry + exit_price) * quantity * (fee_rate + slippage_rate)
            pnl -= costs
            self.state['equity'] = str(D(self.state['equity']) + pnl)
            event = {'event':'paper_exit','side':position['side'],'exit':str(exit_price),
                     'reason':'stop' if hit_stop else 'target','pnl':str(pnl),'timestamp':bar[0]}
            self.state['history'].append(event)
            self.state['position'] = None
            self.save()
            return event
        return None

    def open_position(self, plan, signal_candle):
        if self.state['position'] or self.state['last_signal_candle'] == signal_candle:
            raise ValueError('position already open or duplicate signal')
        self.state['position'] = {**plan,'signal_candle':signal_candle}
        self.state['last_signal_candle'] = signal_candle
        self.state['history'].append({'event':'paper_entry',**self.state['position']})
        self.save()
