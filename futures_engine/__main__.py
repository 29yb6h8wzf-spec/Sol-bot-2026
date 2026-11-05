"""One-shot, read-only Binance futures scanner and persistent paper simulator."""
import json
import os
from decimal import Decimal as D
from dotenv import load_dotenv
from ccxt.base.errors import InvalidOrder
from .core import Config, crossover_signal, plan_trade
from .market import closed_futures_bars
from .paper import PaperLedger
from pathlib import Path
from portfolio_risk import approve


def verified_paper_equity_cap(states):
    """Permit only profits provable from all four existing Paper ledgers.

    Unexplained account injections remain blocked. No Demo/live caller uses this.
    """
    total_cap = D('150')
    for state in states:
        history = state['history']
        if not isinstance(history, list):
            raise ValueError('invalid_paper_history')
        balance = D('37.50')
        peak = balance
        opened = None
        for event in history:
            if not isinstance(event, dict):
                raise ValueError('invalid_paper_history_event')
            if event.get('event') == 'paper_entry':
                if opened is not None or event.get('side') not in ('long', 'short'):
                    raise ValueError('invalid_paper_entry_sequence')
                opened = event
                continue
            if event.get('event') != 'paper_exit' or opened is None:
                raise ValueError('invalid_paper_exit_sequence')
            if event.get('side') != opened['side'] or event.get('reason') not in ('stop', 'target'):
                raise ValueError('invalid_paper_exit')
            entry = D(str(opened['entry']))
            qty = D(str(opened['quantity']))
            exit_price = D(str(event['exit']))
            if event['reason'] == 'stop' and exit_price != D(str(opened['stop'])):
                raise ValueError('invalid_paper_stop_exit')
            if event['reason'] == 'target' and exit_price != D(str(opened['target'])):
                raise ValueError('invalid_paper_target_exit')
            direction = D('1') if opened['side'] == 'long' else D('-1')
            pnl = (exit_price-entry)*direction*qty
            pnl -= (entry+exit_price)*qty*(D('0.0006')+D('0.0005'))
            if not all(v.is_finite() for v in (entry, qty, exit_price, pnl)):
                raise ValueError('nonfinite_paper_profit')
            if min(entry, qty, exit_price) <= 0 or pnl != D(str(event['pnl'])):
                raise ValueError('unverified_paper_profit')
            balance += pnl
            peak = max(peak, balance)
            total_cap += max(D('0'), pnl)
            opened = None
        if not balance.is_finite() or balance <= 0:
            raise ValueError('invalid_paper_balance')
        if balance != D(str(state['equity'])):
            raise ValueError('unreconciled_paper_equity')
        day_start = D(str(state['day_start_equity']))
        if not day_start.is_finite() or day_start <= 0 or day_start > peak:
            raise ValueError('unverified_paper_day_start')
        position = state['position']
        if (opened is None) != (position is None):
            raise ValueError('unreconciled_paper_position')
        if opened is not None and {k: v for k, v in opened.items() if k != 'event'} != position:
            raise ValueError('unreconciled_paper_position')
    return total_cap


def approve_paper_portfolio_entry(raw, amount, leverage, root=Path('/opt/signalpilot')):
    """Fail closed across all four paper ledgers before any new paper entry."""
    try:
        states = [
            json.loads((root / f'paper-ledger-{coin}.json').read_text())
            for coin in ('btc', 'eth', 'sol', 'xrp')
        ]
        total_equity = sum((D(s['equity']) for s in states), D('0'))
        total_start = sum((D(s['day_start_equity']) for s in states), D('0'))
        positions = [s['position'] for s in states if s['position']]
        used_margin = sum((D(pos['margin_estimate']) for pos in positions), D('0'))
        open_risk = sum((D(pos['max_estimated_loss']) for pos in positions), D('0'))
        # Keep the original 150 USDT cap unless a profit above it is
        # reconciled against the actual closed Paper trade history.
        paper_cap = D('150')
        if total_equity > paper_cap or total_start > paper_cap:
            paper_cap = verified_paper_equity_cap(states)
        return approve(total_equity, total_start, used_margin,
                       amount * D(raw['entry']), D(raw['max_estimated_loss']),
                       leverage=leverage, open_risk=open_risk, account_cap=paper_cap)
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
        return False, 'portfolio_state_unavailable'


def main():
    load_dotenv()
    if os.getenv('TRADING_MODE', 'paper').lower() != 'paper':
        raise SystemExit('LIVE TRADING DISABLED: only TRADING_MODE=paper is implemented')
    config = Config(symbol=os.getenv('FUTURES_SYMBOL','BTC/USDT:USDT'),
                    timeframe=os.getenv('TIMEFRAME','15m'),
                    risk_fraction=D(os.getenv('MAX_RISK_FRACTION','0.01')),
                    daily_loss_fraction=D(os.getenv('MAX_DAILY_DRAWDOWN','0.05')),
                    leverage=int(os.getenv('LEVERAGE','2')))
    config.validate()
    ledger = PaperLedger(os.getenv('PAPER_LEDGER','paper-ledger.json'), D(os.getenv('PAPER_START_EQUITY','1000')))
    exchange, market, bars = closed_futures_bars(config.symbol, config.timeframe)
    try:
        ledger.roll_day(bars[-1][0])
        exit_event = ledger.evaluate_exit(bars, config.taker_fee, config.slippage_fraction)
        # Keep EMA warmup stable when the exchange returns 239 or 240 closed candles.
        signal = crossover_signal(bars[-239:])
        result = {'mode':'paper','symbol':config.symbol,'timeframe':config.timeframe,
                  'closed_candle':bars[-1][0],'equity':ledger.state['equity'],
                  'signal':signal,'exit':exit_event,'entry':None}
        if signal and not ledger.state['position'] and ledger.state['last_signal_candle'] != bars[-1][0]:
            limits = market.get('limits') or {}
            minimum = (limits.get('amount') or {}).get('min') or 0
            min_cost = (limits.get('cost') or {}).get('min') or 0
            raw = plan_trade(config,signal,bars[-1][4],ledger.state['equity'],
                             ledger.state['day_start_equity'],amount_step=D('0.00000001'))
            try:
                amount = D(exchange.amount_to_precision(config.symbol, raw['quantity']))
            except InvalidOrder:
                # A quantity below the exchange precision is not a valid paper order.
                result['skip_reason'] = 'below_exchange_precision'
                print(json.dumps(result, ensure_ascii=False))
                return
            if amount <= 0:
                result['skip_reason'] = 'below_exchange_precision'
                print(json.dumps(result, ensure_ascii=False))
                return
            if amount > D(raw['quantity']):
                raise ValueError('exchange precision unexpectedly increased risk')
            if amount < D(str(minimum)) or amount * D(raw['entry']) < D(str(min_cost)):
                result['skip_reason'] = 'below_exchange_minimum'
                print(json.dumps(result, ensure_ascii=False))
                return
            raw['quantity'] = str(amount)
            approved, reason = approve_paper_portfolio_entry(raw, amount, config.leverage)
            if not approved:
                result['portfolio_block'] = reason
                print(json.dumps(result, ensure_ascii=False))
                return
            ledger.open_position(raw,bars[-1][0])
            result['entry'] = raw
        print(json.dumps(result,ensure_ascii=False))
    finally:
        exchange.close() if hasattr(exchange,'close') else None


if __name__ == '__main__':
    main()
