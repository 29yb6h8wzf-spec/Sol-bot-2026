"""Offline, fail-closed portfolio risk arithmetic; never places orders."""
from decimal import Decimal as D
def approve(equity, day_start, used_margin, proposed_notional, proposed_risk, leverage=2, open_risk=0):
    equity,day_start,used_margin,proposed_notional,proposed_risk,open_risk=map(D,map(str,(equity,day_start,used_margin,proposed_notional,proposed_risk,open_risk)))
    if equity<=0 or day_start<=0 or leverage<1 or leverage>2: return False,'invalid_account'
    if min(used_margin,proposed_notional,proposed_risk,open_risk)<0: return False,'invalid_input'
    if day_start-equity>=D('7.50'): return False,'daily_loss_limit'
    if proposed_risk>D('1.50'): return False,'per_trade_risk'
    if proposed_risk+open_risk>min(D('7.50')-(day_start-equity),equity): return False,'portfolio_risk_budget'
    if used_margin+proposed_notional/D(leverage)>equity: return False,'insufficient_margin'
    return True,'approved_offline_only'
