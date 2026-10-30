"""Persistent paper ledger; the CLI holds an exclusive lock for the whole scan."""
import json
import os
import tempfile
from contextlib import contextmanager
from decimal import Decimal as D
from pathlib import Path
from .core import utc_day


@contextmanager
def locked_ledger(path, initial_equity, symbol, timeframe, duration):
    # POSIX advisory locks are released by the OS even after a process crash.
    # Fail closed on platforms without flock; never run an unlocked CLI scan.
    import fcntl
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_name(path.name + '.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('paper ledger is locked by another runner') from exc
        try:
            ledger = PaperLedger(path, initial_equity)
            ledger.bind(symbol, timeframe, duration)
            yield ledger
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


class PaperLedger:
    def __init__(self, path, initial_equity=D('1000')):
        self.path = Path(path)
        initial_equity = D(str(initial_equity))
        if not initial_equity.is_finite() or initial_equity <= 0:
            raise ValueError('invalid initial paper equity')
        if self.path.exists():
            self.state = json.loads(self.path.read_text())
            for key in ('equity', 'day_start_equity'):
                if not D(self.state[key]).is_finite():
                    raise ValueError('invalid ledger equity')
            for key in ('position', 'history', 'day', 'last_signal_candle'):
                if key not in self.state:
                    raise ValueError('incomplete paper ledger')
        else:
            self.state = {'equity':str(initial_equity),'initial_equity':str(initial_equity),
                          'day':None,'day_start_equity':str(initial_equity),
                          'position':None,'last_signal_candle':None,'history':[]}

    def bind(self, symbol, timeframe, duration):
        identity = {'symbol':symbol, 'timeframe':timeframe, 'duration':duration}
        if self.state.get('market') not in (None, identity):
            raise ValueError('ledger belongs to a different market/timeframe')
        if self.state.get('market') is None and (self.state['position'] or self.state['history']):
            raise ValueError('legacy ledger has no market identity; archive it and use a new ledger')
        if self.state.get('market') != identity:
            self.state['market'] = identity
            self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix=self.path.name + '.', suffix='.tmp', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(self.state, stream, indent=2, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def roll_day(self, timestamp):
        day = utc_day(timestamp)
        if self.state['day'] and day < self.state['day']:
            raise ValueError('cannot move ledger day backwards')
        if self.state['day'] != day:
            self.state['day'] = day
            self.state['day_start_equity'] = self.state['equity']
            self.save()

    def evaluate_exit(self, bars, fee_rate, slippage_rate):
        position = self.state['position']
        if not position:
            return None
        duration = self.state.get('market', {}).get('duration', 900000)
        cursor = position.get('last_evaluated_candle', position['signal_candle'])
        pending = [bar for bar in bars if bar[0] > cursor]
        # Never skip unobserved candles after downtime: require explicit recovery.
        for i, bar in enumerate(pending):
            if bar[0] != cursor + (i + 1) * duration:
                raise ValueError('missing paper exit candles; restore complete history before continuing')
        direction = D(1) if position['side'] == 'long' else D(-1)
        stop, target = D(position['stop']), D(position['target'])
        # Execution assumptions are fixed at entry, even if configuration changes.
        fee_rate = D(position.get('fee_rate', str(fee_rate)))
        slippage_rate = D(position.get('slippage_rate', str(slippage_rate)))
        for bar in pending:
            self.roll_day(bar[0])
            opening, high, low = (D(str(value)) for value in bar[1:4])
            hit_stop = low <= stop if direction > 0 else high >= stop
            hit_target = high >= target if direction > 0 else low <= target
            position['last_evaluated_candle'] = bar[0]
            if not (hit_stop or hit_target):
                continue
            gap_stop = opening <= stop if direction > 0 else opening >= stop
            gap_target = opening >= target if direction > 0 else opening <= target
            # The open is observed first. Otherwise ambiguous intrabar touches use stop first.
            reason = 'stop' if gap_stop or (hit_stop and not gap_target) else 'target'
            exit_price = opening if gap_stop else (stop if reason == 'stop' else target)
            quantity, entry = D(position['quantity']), D(position['entry'])
            costs = (entry + exit_price) * quantity * (fee_rate + slippage_rate)
            pnl = (exit_price - entry) * direction * quantity - costs
            self.state['equity'] = str(D(self.state['equity']) + pnl)
            event = {'event':'paper_exit','side':position['side'],'exit':str(exit_price),
                     'reason':reason,'pnl':str(pnl),'costs':str(costs),'timestamp':bar[0]}
            self.state['history'].append(event)
            self.state['position'] = None
            self.save()
            return event
        if pending:
            self.save()
        return None

    def open_position(self, plan, signal_candle):
        previous = self.state['last_signal_candle']
        if self.state['position'] or (previous is not None and signal_candle <= previous):
            raise ValueError('position already open or duplicate/older signal')
        self.state['position'] = {**plan,'signal_candle':signal_candle,
                                  'last_evaluated_candle':signal_candle}
        self.state['last_signal_candle'] = signal_candle
        self.state['history'].append({'event':'paper_entry',**self.state['position']})
        self.save()
