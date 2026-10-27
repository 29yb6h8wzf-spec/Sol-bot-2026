"""One-shot, read-only Binance futures scanner and persistent paper simulator."""
import json
import os
from decimal import Decimal as D
from dotenv import load_dotenv
from .core import Config, plan_trade
from .market import closed_futures_bars
from .paper import locked_ledger
from .indicators import advance_indicators


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
    exchange, market, bars = closed_futures_bars(config.symbol, config.timeframe)
    try:
        with locked_ledger(os.getenv('PAPER_LEDGER','paper-ledger.json'),
                           D(os.getenv('PAPER_START_EQUITY','1000')),
                           config.symbol, config.timeframe,
                           exchange.parse_timeframe(config.timeframe) * 1000) as ledger:
            indicators = advance_indicators(ledger.state.get('indicators'), bars,
                                            exchange.parse_timeframe(config.timeframe)*1000)
            exit_event = ledger.evaluate_exit(bars, config.taker_fee, config.slippage_fraction)
            ledger.roll_day(bars[-1][0])
            signal = indicators['signal']
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
                    raise ValueError('amount below exchange precision')
                if amount > D(raw['quantity']):
                    raise ValueError('exchange precision unexpectedly increased risk')
                if amount < D(str(minimum)) or amount * D(raw['entry']) < D(str(min_cost)):
                    raise ValueError('insufficient balance / exchange dust limit')
                ratio = amount / D(raw['quantity'])
                raw['quantity'] = str(amount)
                for key in ('max_estimated_loss', 'margin_estimate'):
                    raw[key] = str(D(raw[key]) * ratio)
                ledger.open_position(raw,bars[-1][0])
                result['entry'] = raw
            ledger.state['indicators'] = indicators
            ledger.save()
            print(json.dumps(result,ensure_ascii=False))
    finally:
        exchange.close() if hasattr(exchange,'close') else None


if __name__ == '__main__':
    main()
