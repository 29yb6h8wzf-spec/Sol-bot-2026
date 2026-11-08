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
    atr_period: int = 14
    atr_stop_multiple: Decimal = D('1.5')
    atr_reward_multiple: Decimal = D('2')
    max_holding_minutes: int = 15

    def validate(self):
        numeric = (self.risk_fraction, self.daily_loss_fraction, self.stop_fraction,
                   self.reward_multiple, self.taker_fee, self.slippage_fraction,
                   self.atr_stop_multiple, self.atr_reward_multiple)
        if any(not x.is_finite() for x in numeric):
            raise ValueError('non-finite paper risk configuration')
        if not (D('0') < self.risk_fraction <= D('0.01')):
            raise ValueError('risk must be between 0 and 1%')
        if not (D('0') < self.daily_loss_fraction <= D('0.05')):
            raise ValueError('daily drawdown must be between 0 and 5%')
        if not (1 <= self.leverage <= 2):
            raise ValueError('leverage capped at 2x for paper testing')
        if not (D('0') < self.stop_fraction <= D('0.05') and self.reward_multiple >= 1):
            raise ValueError('invalid stop/reward')
        if not (2 <= self.atr_period <= 100 and self.atr_stop_multiple > 0 and
                self.atr_reward_multiple >= 1 and 1 <= self.max_holding_minutes <= 1440):
            raise ValueError('invalid ATR/time-exit configuration')
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
    if any(not x.is_finite() or x <= 0 for x in prices):
        raise ValueError('invalid candle prices')
    fast_before, slow_before = ema(prices[:-1], 50), ema(prices[:-1], 200)
    fast_now, slow_now = ema(prices, 50), ema(prices, 200)
    momentum = rsi(prices)
    if fast_before <= slow_before and fast_now > slow_now and momentum < 55:
        return 'long'
    if fast_before >= slow_before and fast_now < slow_now and momentum > 45:
        return 'short'
    return None


def atr(closed_bars, period=14):
    """Wilder ATR using completed OHLC candles only."""
    if len(closed_bars) < period + 1:
        raise ValueError('insufficient ATR candles')
    true_ranges = []
    for prev, bar in zip(closed_bars[:-1], closed_bars[1:]):
        high, low, previous_close = D(str(bar[2])), D(str(bar[3])), D(str(prev[4]))
        if not all(v.is_finite() and v > 0 for v in (high, low, previous_close)) or low > high:
            raise ValueError('invalid ATR candle')
        true_ranges.append(max(high-low, abs(high-previous_close), abs(low-previous_close)))
    result = sum(true_ranges[:period], D(0)) / D(period)
    for value in true_ranges[period:]:
        result = (result * D(period-1) + value) / D(period)
    return result


def plan_trade(config, side, entry, equity, day_start_equity, minimum_amount=D('0'), amount_step=D('0.001'), min_cost=D('0'), stop_fraction_override=None):
    config.validate()
    entry, equity, day_start_equity = D(str(entry)), D(str(equity)), D(str(day_start_equity))
    if (side not in ('long', 'short') or
        not all(x.is_finite() and x > 0 for x in (entry, equity, day_start_equity))):
        raise ValueError('invalid trade inputs')
    if equity <= day_start_equity * (D(1) - config.daily_loss_fraction):
        raise ValueError('daily drawdown circuit breaker is active')
    direction = D(1) if side == 'long' else D(-1)
    stop_fraction = config.stop_fraction if stop_fraction_override is None else D(str(stop_fraction_override))
    if not stop_fraction.is_finite() or not D(0) < stop_fraction <= D('0.05'):
        raise ValueError('ATR stop outside configured safety bounds')
    stop = entry * (D(1) - direction * stop_fraction)
    target = entry * (D(1) + direction * stop_fraction * (config.atr_reward_multiple if stop_fraction_override is not None else config.reward_multiple))
    loss_per_unit = abs(entry - stop) + (entry + stop) * (config.taker_fee + config.slippage_fraction)
    risk_budget = min(equity * config.risk_fraction, equity - day_start_equity * (D(1) - config.daily_loss_fraction))
    if risk_budget <= 0 or loss_per_unit <= 0:
        raise ValueError('no risk budget available')
    qty = min(risk_budget / loss_per_unit, equity * config.leverage / entry)
    amount_step = D(str(amount_step))
    if not amount_step.is_finite() or amount_step <= 0:
        raise ValueError('invalid exchange amount step')
    qty = (qty / amount_step).to_integral_value(rounding=ROUND_DOWN) * amount_step
    minimum_amount, min_cost = D(str(minimum_amount)), D(str(min_cost))
    if not all(x.is_finite() and x >= 0 for x in (minimum_amount, min_cost)):
        raise ValueError('invalid exchange minimums')
    if qty <= 0 or qty < minimum_amount or qty * entry < min_cost:
        raise ValueError('insufficient balance or dust amount after rounding')
    return {'side':side,'entry':str(entry),'stop':str(stop),'target':str(target),
            'quantity':str(qty),'max_estimated_loss':str(qty * loss_per_unit),
            'margin_estimate':str(qty * entry / D(config.leverage)),
            'risk_budget':str(risk_budget)}


def utc_day(ts_ms):
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
