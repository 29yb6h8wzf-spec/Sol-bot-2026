"""Pure strategy and risk calculations; no exchange order methods exist here."""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN

D = Decimal


@dataclass(frozen=True)
class Config:
    symbol: str = 'BTC/USDT:USDT'
    timeframe: str = '15m'
    risk_fraction: Decimal = D('0.01')
    daily_loss_fraction: Decimal = D('0.05')
    leverage: int = 2
    stop_fraction: Decimal = D('0.02')
    reward_multiple: Decimal = D('2')
    taker_fee: Decimal = D('0.0006')
    slippage_fraction: Decimal = D('0.0005')

    def validate(self):
        if not (D('0') < self.risk_fraction <= D('0.01')):
            raise ValueError('risk must be between 0 and 1%')
        if not (D('0') < self.daily_loss_fraction <= D('0.05')):
            raise ValueError('daily drawdown must be between 0 and 5%')
        if not (1 <= self.leverage <= 2):
            raise ValueError('leverage capped at 2x for paper testing')
        if not (D('0') < self.stop_fraction <= D('0.05') and self.reward_multiple >= 1):
            raise ValueError('invalid stop/reward')
        if self.taker_fee < 0 or self.slippage_fraction < 0:
            raise ValueError('invalid execution costs')


def ema(values, length):
    if len(values) < length:
        raise ValueError('insufficient EMA candles')
    alpha = D(2) / D(length + 1)
    result = sum(values[:length]) / D(length)
    for value in values[length:]:
        result = alpha * value + (D(1) - alpha) * result
    return result


def rsi(values, period=14):
    if len(values) < period + 1:
        raise ValueError('insufficient RSI candles')
    diffs = [values[i] - values[i-1] for i in range(1, len(values))]
    gains = [max(D(0), x) for x in diffs]
    losses = [max(D(0), -x) for x in diffs]
    gain = sum(gains[:period]) / D(period)
    loss = sum(losses[:period]) / D(period)
    for i in range(period, len(diffs)):
        gain = (gain * (period - 1) + gains[i]) / D(period)
        loss = (loss * (period - 1) + losses[i]) / D(period)
    if loss == 0:
        return D(100) if gain else D(50)
    return D(100) - D(100) / (D(1) + gain / loss)


def crossover_signal(closed_bars):
    """Use only closed candles; EMA50/200 crossover filtered by RSI14."""
    if len(closed_bars) < 202:
        raise ValueError('at least 202 closed bars required')
    prices = [D(str(row[4])) for row in closed_bars]
    if any(x <= 0 for x in prices):
        raise ValueError('invalid candle prices')
    fast_before, slow_before = ema(prices[:-1], 50), ema(prices[:-1], 200)
    fast_now, slow_now = ema(prices, 50), ema(prices, 200)
    momentum = rsi(prices)
    if fast_before <= slow_before and fast_now > slow_now and momentum < 55:
        return 'long'
    if fast_before >= slow_before and fast_now < slow_now and momentum > 45:
        return 'short'
    return None


def plan_trade(config, side, entry, equity, day_start_equity, minimum_amount=D('0'), amount_step=D('0.001'), min_cost=D('0')):
    config.validate()
    entry, equity, day_start_equity = D(str(entry)), D(str(equity)), D(str(day_start_equity))
    if side not in ('long', 'short') or min(entry, equity, day_start_equity) <= 0:
        raise ValueError('invalid trade inputs')
    if equity <= day_start_equity * (D(1) - config.daily_loss_fraction):
        raise ValueError('daily drawdown circuit breaker is active')
    direction = D(1) if side == 'long' else D(-1)
    stop = entry * (D(1) - direction * config.stop_fraction)
    target = entry * (D(1) + direction * config.stop_fraction * config.reward_multiple)
    loss_per_unit = abs(entry - stop) + (entry + stop) * (config.taker_fee + config.slippage_fraction)
    risk_budget = min(equity * config.risk_fraction, equity - day_start_equity * (D(1) - config.daily_loss_fraction))
    if risk_budget <= 0 or loss_per_unit <= 0:
        raise ValueError('no risk budget available')
    qty = min(risk_budget / loss_per_unit, equity * config.leverage / entry)
    amount_step = D(str(amount_step))
    if amount_step <= 0:
        raise ValueError('invalid exchange amount step')
    qty = (qty / amount_step).to_integral_value(rounding=ROUND_DOWN) * amount_step
    if qty <= 0 or qty < D(str(minimum_amount)) or qty * entry < D(str(min_cost)):
        raise ValueError('insufficient balance or dust amount after rounding')
    return {'side':side,'entry':str(entry),'stop':str(stop),'target':str(target),
            'quantity':str(qty),'max_estimated_loss':str(qty * loss_per_unit),
            'margin_estimate':str(qty * entry / D(config.leverage)),
            'risk_budget':str(risk_budget)}


def utc_day(ts_ms):
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
