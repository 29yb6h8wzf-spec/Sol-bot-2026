"""Offline, research-inspired cross-sectional crypto momentum baseline.
Reference: Fischer et al. (2019), Statistical Arbitrage in Cryptocurrency Markets.
This is NOT a reproduction of the paper's trained 40-coin random forest.
Uses only past closed bars; no exchange APIs or order execution.
"""
from decimal import Decimal


def evaluate(prices, *, lookback=24, holding=24, fee_per_side="0.0006", slippage_per_side="0.0005"):
    if not isinstance(prices,dict) or len(prices)<4: raise ValueError("need_at_least_four_assets")
    if type(lookback) is not int or type(holding) is not int or lookback<1 or holding<1:raise ValueError("invalid_windows")
    fee=Decimal(str(fee_per_side));slip=Decimal(str(slippage_per_side))
    if not fee.is_finite() or not slip.is_finite() or fee<0 or slip<0:raise ValueError("invalid_costs")
    symbols=sorted(prices)
    length=len(prices[symbols[0]])
    if length<lookback+holding+2:raise ValueError("insufficient_history")
    for symbol in symbols:
        rows=prices[symbol]
        if len(rows)!=length:raise ValueError("unaligned_history")
        for j,row in enumerate(rows):
            if len(row)!=6 or type(row[0]) is not int:raise ValueError("invalid_candle")
            if j and row[0]!=rows[j-1][0]+300000:raise ValueError("gapped_history")
            if row[0]!=prices[symbols[0]][j][0]:raise ValueError("unaligned_history")
            if not all(Decimal(str(v)).is_finite() for v in row[1:]):raise ValueError("invalid_candle")
            if any(Decimal(str(row[k]))<=0 for k in (1,2,3,4)):raise ValueError("invalid_candle")
            if Decimal(str(row[2]))<max(Decimal(str(row[1])),Decimal(str(row[4]))) or Decimal(str(row[3]))>min(Decimal(str(row[1])),Decimal(str(row[4]))):raise ValueError("invalid_candle")
    trades=[]
    for i in range(lookback,length-holding-1,holding):
        ranks=sorted(symbols,key=lambda s: (Decimal(str(prices[s][i][4]))/Decimal(str(prices[s][i-lookback][4]))-1,s))
        for symbol,direction in ((ranks[0],-1),(ranks[-1],1)):
            entry=Decimal(str(prices[symbol][i+1][1]))*(1+slip*direction)
            exit_price=Decimal(str(prices[symbol][i+holding][4]))*(1-slip*direction)
            net=(exit_price-entry)*direction/entry-fee*(1+exit_price/entry)
            trades.append({"symbol":symbol,"direction":"LONG" if direction==1 else "SHORT","signal_ms":prices[symbol][i][0],"exit_ms":prices[symbol][i+holding][0],"net_return_pct":float(net*100)})
    n=len(trades)
    return {"status":"OFFLINE_RESEARCH_ONLY","orders_sent":False,"method":"lagged_return_rank_long_top_short_bottom","paper_exact_replication":False,"trades":n,"wins":sum(x["net_return_pct"]>0 for x in trades),"mean_net_return_pct":sum(x["net_return_pct"] for x in trades)/n if n else None,"trade_log":trades,"funding_included":False,"position_sizing_included":False}
