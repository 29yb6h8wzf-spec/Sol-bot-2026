"""One-shot, read-only Binance futures scanner and persistent paper simulator."""
import json
import os
from decimal import Decimal as D
from dotenv import load_dotenv
from .core import Config, crossover_signal, plan_trade
from .market import closed_futures_bars
from .paper import PaperLedger
from pathlib import Path
from portfolio_risk import approve


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
        return approve(total_equity, total_start, used_margin,
                       amount * D(raw['entry']), D(raw['max_estimated_loss']),
                       leverage=leverage, open_risk=open_risk)
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
        signal = crossover_signal(bars)
        result = {'mode':'paper','symbol':config.symbol,'timeframe':config.timeframe,
                  'closed_candle':bars[-1][0],'equity':ledger.state['equity'],
                  'signal':signal,'exit':exit_event,'entry':None}
        if signal and not ledger.state['position'] and ledger.state['last_signal_candle'] != bars[-1][0]:
            limits = market.get('limits') or {}
            minimum = (limits.get('amount') or {}).get('min') or 0
            min_cost = (limits.get('cost') or {}).get('min') or 0
            raw = plan_trade(config,signal,bars[-1][4],ledger.state['equity'],
                             ledger.state['day_start_equity'],amount_step=D('0.00000001'))
            amount = D(exchange.amount_to_precision(config.symbol,raw['quantity']))
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
