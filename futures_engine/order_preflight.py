"""Offline Binance Futures order intent preflight. No API calls or order placement."""
from decimal import Decimal as D, InvalidOperation
from portfolio_risk import approve
SYMBOLS = frozenset({'BTC/USDT:USDT','ETH/USDT:USDT','SOL/USDT:USDT','XRP/USDT:USDT'})
def check(intent, account):
    try:
        if intent.get('symbol') not in SYMBOLS: return False,'symbol_not_allowed'
        if intent.get('side') not in ('long','short'): return False,'side_not_allowed'
        if intent.get('source') != 'verified_85_score_engine': return False,'unverified_signal_source'
        score=D(str(intent['score']))
        if not D('85')<=score<=D('100'): return False,'score_below_85'
        entry,stop,target,qty=map(lambda k:D(str(intent[k])),('entry','stop','target','quantity'))
        if min(entry,stop,target,qty)<=0: return False,'invalid_price_or_quantity'
        if intent['side']=='long' and not stop<entry<target: return False,'invalid_long_brackets'
        if intent['side']=='short' and not target<entry<stop: return False,'invalid_short_brackets'
        risk=qty*abs(entry-stop)
        if "estimated_loss_including_buffer" in intent:
            buffered = D(str(intent["estimated_loss_including_buffer"]))
            if not buffered.is_finite() or buffered < risk:
                return False, "invalid_buffered_risk"
            risk = buffered
        return approve(account['equity'],account['day_start'],account['used_margin'],entry*qty,risk,leverage=account.get('leverage',2),open_risk=account.get('open_risk',0))
    except (KeyError,TypeError,ValueError,InvalidOperation): return False,'malformed_order_intent'
