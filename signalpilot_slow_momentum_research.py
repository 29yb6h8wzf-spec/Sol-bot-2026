"""Offline-only slow momentum research for SOL/XRP. No exchange or execution code."""

def evaluate(rows, *, starting_usd=75., leverage=2., lookback_bars=864, hold_bars=288, fee_rate=.0006, slip_rate=.0005, start_index=None, end_index=None):
    if len(rows)<lookback_bars+hold_bars+2 or min(starting_usd,leverage,lookback_bars,hold_bars)<=0:raise ValueError("invalid_configuration")
    if fee_rate<0 or slip_rate<0:raise ValueError("invalid_costs")
    start=max(lookback_bars, start_index or 0);end=min(len(rows),end_index or len(rows));balance=float(starting_usd);trades=[];peak=balance;drawdown=0.
    for i in range(start,end-hold_bars-1,hold_bars):
        direction=1 if rows[i][4]>rows[i-lookback_bars][4] else -1
        entry=rows[i+1][1]*(1+direction*slip_rate);exit_price=rows[i+hold_bars][4]*(1-direction*slip_rate)
        net=direction*(exit_price-entry)/entry-fee_rate*(1+exit_price/entry)
        pnl=balance*leverage*net;balance+=pnl;peak=max(peak,balance);drawdown=max(drawdown,(peak-balance)/peak)
        trades.append({"signal_ms":rows[i][0],"exit_ms":rows[i+hold_bars][0],"direction":direction,"net_return_pct":100*net,"pnl_usd":pnl})
        if balance<=0:break
    return {"status":"OFFLINE_RESEARCH_ONLY","orders_sent":False,"starting_usd":starting_usd,"ending_usd":round(balance,2),"pnl_usd":round(balance-starting_usd,2),"trades":len(trades),"wins":sum(t["pnl_usd"]>0 for t in trades),"max_drawdown_pct":round(drawdown*100,2),"funding_included":False,"liquidation_included":False,"trade_log":trades}
