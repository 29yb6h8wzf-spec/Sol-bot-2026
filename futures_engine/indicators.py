"""Versioned, incremental EMA/RSI state shared by replay and paper scans."""
from copy import deepcopy
from decimal import Decimal as D
from .core import ema

WARMUP_BARS = 1000


def _signal(fast_before, slow_before, fast, slow, gain, loss):
    momentum = (D(100) if gain else D(50)) if loss == 0 else D(100)-D(100)/(1+gain/loss)
    if fast_before <= slow_before and fast > slow and momentum < 55:
        return 'long'
    if fast_before >= slow_before and fast < slow and momentum > 45:
        return 'short'
    return None


def advance_indicators(saved, bars, duration):
    """Return a new JSON-safe state; never mutate saved state on failure.

    Initial seed needs 1000 closed bars. Subsequent scans consume only unseen
    contiguous bars. The last signal is retained for idempotent scan retries.
    """
    if not bars or not isinstance(duration, int) or duration <= 0:
        raise ValueError('invalid indicator candles/duration')
    prices = []
    for i, bar in enumerate(bars):
        price = D(str(bar[4]))
        if (not price.is_finite() or price <= 0 or not isinstance(bar[0], int)
            or bar[0] < 0 or bar[0] % duration
            or (i and bar[0] != bars[i-1][0]+duration)):
            raise ValueError('invalid or gapped indicator candles')
        prices.append(price)
    if saved is None:
        if len(bars) < WARMUP_BARS:
            raise ValueError('at least 1000 closed candles required for indicator warmup')
        diffs = [prices[i]-prices[i-1] for i in range(1,200)]
        gain = sum(max(D(0), x) for x in diffs[:14])/14
        loss = sum(max(D(0), -x) for x in diffs[:14])/14
        for diff in diffs[14:]:
            gain = (gain*13+max(D(0), diff))/14
            loss = (loss*13+max(D(0), -diff))/14
        state = {'version':1, 'duration':duration, 'origin':bars[0][0],
                 'last_candle':bars[199][0], 'close':str(prices[199]),
                 'fast':str(ema(prices[:200],50)), 'slow':str(ema(prices[:200],200)),
                 'gain':str(gain), 'loss':str(loss), 'signal':None}
    else:
        state = deepcopy(saved)
        try:
            if (state['version'] != 1 or state['duration'] != duration
                or state['signal'] not in (None,'long','short')
                or not isinstance(state['last_candle'], int)
                or state['last_candle'] % duration):
                raise ValueError('invalid indicator state identity')
            for key in ('close','fast','slow','gain','loss'):
                value = D(state[key])
                if not value.is_finite() or value < 0 or (key in ('close','fast','slow') and value == 0):
                    raise ValueError('invalid indicator numeric state')
        except (KeyError, TypeError, ArithmeticError) as exc:
            raise ValueError('invalid indicator state') from exc
        if bars[-1][0] < state['last_candle']:
            raise ValueError('indicator candles moved backwards')
        for bar, price in zip(bars,prices):
            if bar[0] == state['last_candle'] and price != D(state['close']):
                raise ValueError('previously processed candle was revised')
    for bar, price in zip(bars,prices):
        if bar[0] <= state['last_candle']:
            continue
        if bar[0] != state['last_candle'] + duration:
            raise ValueError('missing indicator history; backfill before continuing')
        fast_before, slow_before = D(state['fast']), D(state['slow'])
        fast_alpha, slow_alpha = D(2)/51, D(2)/201
        fast = fast_alpha*price+(1-fast_alpha)*fast_before
        slow = slow_alpha*price+(1-slow_alpha)*slow_before
        diff = price-D(state['close'])
        gain = (D(state['gain'])*13+max(D(0),diff))/14
        loss = (D(state['loss'])*13+max(D(0),-diff))/14
        state.update(last_candle=bar[0], close=str(price), fast=str(fast), slow=str(slow),
                     gain=str(gain), loss=str(loss),
                     signal=_signal(fast_before,slow_before,fast,slow,gain,loss))
    return state
