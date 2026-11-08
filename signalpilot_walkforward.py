"""Offline research-only walk-forward replay of actual SignalPilot candidates().
No API, orders, funding, sizing or claims of profitability certification.
Input: closed historical [open_ms,open,high,low,close,volume] candles.
"""
from decimal import Decimal as D
from strategies import candidates

def _check(rows, step):
    if not isinstance(rows,list) or len(rows)<210: raise ValueError("insufficient_history")
    prev=None
    for row in rows:
        if len(row)!=6 or type(row[0]) is not int or row[0]%step: raise ValueError("invalid_candle")
        _,o,h,l,c,v=row
        a=list(map(lambda x:D(str(x)),(o,h,l,c,v)))
        if not all(x.is_finite() for x in a) or min(a[:4])<=0 or a[4]<0 or a[1]<max(a[0],a[3]) or a[2]>min(a[0],a[3]): raise ValueError("invalid_ohlcv")
        if prev is not None and row[0]!=prev+step: raise ValueError("gapped_candles")
        prev=row[0]

def _view(rows):
    return [{"time":r[0],"high":float(r[2]),"low":float(r[3]),"close":float(r[4]),"volume":float(r[5])} for r in rows]

def evaluate(five,four,*,thresholds=(70,75,80,85),fee_rate="0.0006",slippage_rate="0.0005",max_holding_bars=48,allowed_strategies=None):
    _check(five,300000);_check(four,14400000)
    fee,slip=D(fee_rate),D(slippage_rate)
    if fee<0 or slip<0 or not 1<=max_holding_bars<=288: raise ValueError("invalid_assumptions")
    if allowed_strategies is not None and (not isinstance(allowed_strategies,(tuple,list,set,frozenset)) or not allowed_strategies or any(s not in ("EMA_ADX","RSI_BOLL","MACD_VOLUME") for s in allowed_strategies)):\n        raise ValueError("invalid_strategy_filter")\n    f=_view(five);h=_view(four);output={}
    for threshold in thresholds:
        if type(threshold) is not int or not 0<=threshold<=100: raise ValueError("invalid_threshold")
        trades=[];next_free=209;blocked=0
        for i in range(209,len(five)-1):
            if i<next_free:continue
            decision=five[i][0]+300000
            historical=[x for x in h if x["time"]+14400000<=decision]
            if len(historical)<100:continue
            setups,_=candidates(f[max(0,i-239):i+1],historical[-240:])
            available=sorted((x for x in setups if x["score"]>=threshold and (allowed_strategies is None or x["strategy"] in allowed_strategies)),key=lambda x:-x["score"])
            if not available:blocked+=1;continue
            signal=available[0];direction=1 if signal["direction"]=="LONG" else -1
            atr=D(str(signal["atr"]))
            if not atr.is_finite() or atr<=0:continue
            entry=D(str(five[i+1][1]))*(1+slip*direction)
            stop=entry-direction*atr;target=entry+direction*atr*D("1.5")
            if stop<=0 or target<=0:continue
            last=min(i+max_holding_bars,len(five)-1);reason="TIME";exit_index=last;raw_exit=D(str(five[last][4]))
            for j in range(i+1,last+1):
                opening,high,low=map(lambda k:D(str(five[j][k])),(1,2,3))
                hit_stop=low<=stop if direction==1 else high>=stop
                hit_target=high>=target if direction==1 else low<=target
                if hit_stop or hit_target:
                    reason="STOP" if hit_stop else "TARGET"
                    raw_exit=(min(stop,opening) if direction==1 else max(stop,opening)) if hit_stop else target
                    exit_index=j;break
            exit_fill=raw_exit*(1-slip*direction)
            net=(exit_fill-entry)*direction/entry-fee*(1+exit_fill/entry)
            trades.append({"strategy":signal["strategy"],"direction":signal["direction"],"score":signal["score"],"signal_ms":five[i][0],"exit_ms":five[exit_index][0],"reason":reason,"net_return_pct":float(net*100)})
            next_free=exit_index+1
        output[str(threshold)]={"trades":len(trades),"wins":sum(t["net_return_pct"]>0 for t in trades),"sum_net_return_pct_uncompounded":sum(t["net_return_pct"] for t in trades),"no_signal_bars":blocked,"trade_log":trades}
    return {"status":"OFFLINE_RESEARCH_ONLY","orders_sent":False,"funding_included":False,"position_sizing_included":False,"allowed_strategies":sorted(allowed_strategies) if allowed_strategies is not None else None,"fee_rate":str(fee),"slippage_rate":str(slip),"thresholds":output}
