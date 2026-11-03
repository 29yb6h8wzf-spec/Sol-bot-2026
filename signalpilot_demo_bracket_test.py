"""One-shot Binance USDT-M DEMO bracket test. Never connects to live.

Requires explicitly setting DEMO_TEST_CONFIRM=YES. Uses AWS secret Demobinance.
Only run on a dedicated demo account with no pre-existing XRP exposure.
"""
import json
import os
import sys
from decimal import Decimal

import boto3
import ccxt

SYMBOL = 'XRP/USDT:USDT'


def demo_exchange():
    raw = boto3.client('secretsmanager', region_name='il-central-1').get_secret_value(SecretId='Demobinance')['SecretString']
    keys = json.loads(raw)
    exchange = ccxt.binanceusdm({'apiKey': keys['apiKey'], 'secret': keys['secret'], 'enableRateLimit': True, 'timeout': 20000})
    exchange.enable_demo_trading(True)
    if 'demo-fapi.binance.com' not in str(exchange.urls['api']):
        raise RuntimeError('Demo endpoint not confirmed')
    return exchange


def exposure(exchange):
    return sum(Decimal(str(p.get('contracts') or 0)) for p in exchange.fetch_positions([SYMBOL]) if p.get('symbol') == SYMBOL)


def algos(exchange):
    data = exchange.fapiPrivateGetOpenAlgoOrders({'symbol': exchange.market_id(SYMBOL)})
    return data.get('orders', []) if isinstance(data, dict) else data


def main():
    if os.getenv('DEMO_TEST_CONFIRM') != 'YES':
        print('PREPARED ONLY: set DEMO_TEST_CONFIRM=YES to authorize demo order test')
        return 0
    e = demo_exchange()
    e.load_markets()
    if exposure(e) != 0 or e.fetch_open_orders(SYMBOL) or algos(e):
        raise RuntimeError('Demo XRP already has exposure/orders: refusing to run')
    if e.fetch_position_mode(SYMBOL).get('hedged') is not False:
        raise RuntimeError('One-way mode required; refusing to change account settings')
    e.set_leverage(2, SYMBOL)
    ticker = e.fetch_ticker(SYMBOL)
    price = Decimal(str(ticker['last']))
    if price <= 0:
        raise RuntimeError('Invalid market price')
    qty = Decimal(str(e.amount_to_precision(SYMBOL, str(Decimal('10') / price))))
    market = e.market(SYMBOL)
    min_qty = Decimal(str((market.get('limits', {}).get('amount') or {}).get('min') or 0))
    min_cost = Decimal(str((market.get('limits', {}).get('cost') or {}).get('min') or 0))
    if qty < min_qty or qty * price < min_cost or qty * price > Decimal('15'):
        raise RuntimeError('Safe small quantity not supported by exchange minimums')
    stop = e.price_to_precision(SYMBOL, str(price * Decimal('0.985')))
    target = e.price_to_precision(SYMBOL, str(price * Decimal('1.015')))
    if not (Decimal(stop) < price < Decimal(target)):
        raise RuntimeError('Invalid bracket')
    entry_sent = False
    try:
        print('DEMO_ENTRY_SUBMITTING', flush=True)
        entry_sent = True  # Treat uncertain API responses as possible entry
        e.create_order(SYMBOL, 'market', 'buy', float(qty))
        actual = exposure(e)
        if actual <= 0:
            raise RuntimeError('Entry not confirmed: manual review required')
        sym = e.market_id(SYMBOL)
        def protect(kind, trigger):
            return e.fapiPrivatePostAlgoOrder({'algoType':'CONDITIONAL', 'symbol':sym,
                'side':'SELL', 'type':kind, 'triggerPrice':trigger,
                'closePosition':'true', 'workingType':'MARK_PRICE'})
        sl = protect('STOP_MARKET', stop)
        tp = protect('TAKE_PROFIT_MARKET', target)
        active = {str(o.get('algoId')) for o in algos(e)}
        if str(sl.get('algoId')) not in active or str(tp.get('algoId')) not in active:
            raise RuntimeError('Protective orders not confirmed')
        print('DEMO_BRACKET_VERIFIED', flush=True)
    finally:
        if entry_sent:
            try:
                e.fapiPrivateDeleteAlgoOpenOrders({'symbol': e.market_id(SYMBOL)})
                e.cancel_all_orders(SYMBOL)
                open_qty = exposure(e)
                if open_qty > 0:
                    e.create_order(SYMBOL, 'market', 'sell', float(open_qty), None, {'reduceOnly': True})
                if exposure(e) != 0 or e.fetch_open_orders(SYMBOL) or algos(e):
                    raise RuntimeError('DEMO_CLEANUP_INCOMPLETE: manual intervention required')
                print('DEMO_CLEANUP_VERIFIED', flush=True)
            except Exception as exc:
                print('CRITICAL_DEMO_CLEANUP_FAILED: check demo account manually', type(exc).__name__, flush=True)
                raise
    return 0

if __name__ == '__main__':
    sys.exit(main())
