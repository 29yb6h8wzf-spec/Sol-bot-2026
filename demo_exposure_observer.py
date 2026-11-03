"""Read-only Binance Demo exposure observer. Does not submit orders."""
from demo_account_observer import demo_exchange, assert_demo, save_observation
from decimal import Decimal
import time

OUTPUT = '/opt/signalpilot/demo-exposure-observation.json'

def observe(exchange, now=None):
    assert_demo(exchange)
    positions = exchange.fetch_positions()
    if not isinstance(positions, list):
        raise ValueError('invalid_positions')
    exposed = []
    total = Decimal('0')
    for p in positions:
        raw_contracts = p.get('contracts')
        if raw_contracts is None:
            raw_contracts = (p.get('info') or {}).get('positionAmt')
        if raw_contracts is None:
            raise ValueError('missing_position_quantity')
        contracts = Decimal(str(raw_contracts))
        if not contracts.is_finite():
            raise ValueError('invalid_contracts')
        if contracts == 0:
            continue
        raw = p.get('unrealizedPnl')
        if raw is None:
            raw = (p.get('info') or {}).get('unRealizedProfit')
        if raw is None:
            raise ValueError('missing_unrealized_pnl')
        pnl = Decimal(str(raw))
        if not pnl.is_finite():
            raise ValueError('invalid_unrealized_pnl')
        total += pnl
        exposed.append(str(p['symbol']))
    return {'source': 'binance_demo_account_wide_unrealized_read_only',
            'observed_at': int(time.time()) if now is None else int(now),
            'unrealized_pnl_usdt': str(total),
            'open_position_count': len(exposed),
            'exposed_symbols': sorted(exposed),
            'allocation_ledger_reconciled': False,
            'risk_snapshot_approved': False,
            'execution_authorized': False,
            'orders_sent': False}

def main():
    exchange = demo_exchange()
    try:
        save_observation(observe(exchange), OUTPUT)
    finally:
        if hasattr(exchange, 'close'):
            exchange.close()

if __name__ == '__main__':
    main()
