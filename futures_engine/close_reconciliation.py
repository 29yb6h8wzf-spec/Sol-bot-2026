"""Read-only reconciliation of a previously submitted reduce-only close."""
from decimal import Decimal, InvalidOperation


def flat_account(snapshot):
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get('positions'), list):
        return False
    try:
        values = [snapshot['totalInitialMargin'], snapshot['totalOpenOrderInitialMargin']]
        values.extend(p['positionAmt'] for p in snapshot['positions'])
        return all(Decimal(str(v)).is_finite() and Decimal(str(v)) == 0 for v in values)
    except (KeyError, TypeError, InvalidOperation):
        return False


def reconcile_closing(exchange, signal_id):
    # Never submit another order, cancel protection, or infer success from an error.
    parts = signal_id.split('-')
    if len(parts) != 3 or parts[0] != 'vb' or parts[1] not in ('SOLUSDT', 'XRPUSDT') or not parts[2].isdigit():
        return 'halt_unresolved_execution'
    symbol = parts[1]
    snapshot = exchange.fapiPrivateV3GetAccount()
    if not flat_account(snapshot):
        return 'halt_close_unconfirmed'
    order = exchange.fapiPrivateGetOrder({'symbol': symbol, 'origClientOrderId': signal_id + '-X'})
    try:
        qty, executed = Decimal(str(order['origQty'])), Decimal(str(order['executedQty']))
        confirmed = (order['symbol'] == symbol and order['clientOrderId'] == signal_id + '-X'
                     and order['status'] == 'FILLED' and order['reduceOnly'] is True
                     and qty.is_finite() and executed.is_finite() and qty > 0 and executed == qty)
    except (KeyError, TypeError, InvalidOperation):
        confirmed = False
    if not confirmed:
        return 'halt_close_unconfirmed'
    orders = exchange.fapiPrivateGetOpenOrders({'symbol': symbol})
    algos = exchange.fapiPrivateGetOpenAlgoOrders({'symbol': symbol})
    if isinstance(algos, dict):
        algos = algos.get('orders')
    if not isinstance(orders, list) or not isinstance(algos, list):
        return 'halt_close_unconfirmed'
    if orders or algos:
        return 'halt_close_cleanup_required'
    if not flat_account(exchange.fapiPrivateV3GetAccount()):
        return 'halt_close_unconfirmed'
    return 'closed'
