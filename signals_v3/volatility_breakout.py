"""Research-only 1m volatility breakout, no exchange integration."""
from statistics import mean
from signals_v2.contracts import Candle,DataRejected,MINUTE_MS,FIVE_MINUTES_MS
from signals_v3.spec import SPEC
from signals_v3.trend_pullback import ResearchSignal

def volatility_breakout(symbol: str,five: tuple[Candle,...],one: tuple[Candle,...],decision_ms: int):
    SPEC.validate()
    if not isinstance(five,tuple) or len(five)<64 or not isinstance(one,tuple) or len(one)<45:
        raise DataRejected("insufficient_v3_history")
    for bars,period in ((five,FIVE_MINUTES_MS),(one,MINUTE_MS)):
        for bar in bars:bar.validate(period,decision_ms)
        if any(b.open_ms-a.open_ms!=period for a,b in zip(bars,bars[1:])):
            raise DataRejected("missing_or_duplicate_bar")
        if decision_ms-bars[-1].close_ms(period)>period:
            raise DataRejected("stale_v3_history")
    if one[-1].close_ms(MINUTE_MS)<five[-1].close_ms(FIVE_MINUTES_MS):
        raise DataRejected("one_minute_precedes_five_minute")
    # Exclude the trigger bar from all breakout thresholds and baselines.
    base=one[-21:-1]
    older=one[-41:-21]
    baseline_volume=mean(x.volume for x in base)
    if baseline_volume<=0:raise DataRejected("zero_volume_baseline")
    recent_range=max(x.high for x in base)-min(x.low for x in base)
    older_range=max(x.high for x in older)-min(x.low for x in older)
    if older_range<=0:raise DataRejected("zero_range_baseline")
    if recent_range/older_range>0.85:return ()
    last=one[-1]
    if last.volume/baseline_volume<1.5:return ()
    high=max(x.high for x in base)
    low=min(x.low for x in base)
    direction="LONG" if last.close>high else "SHORT" if last.close<low else None
    if direction is None:return ()
    atr=mean(max(c.high-c.low,abs(c.high-p.close),abs(c.low-p.close))
             for p,c in zip(five[-15:-1],five[-14:]))
    if atr<=0:raise DataRejected("zero_atr")
    entry=last.close
    if direction=="LONG":
        stop=min(low,entry-atr)-0.1*atr
        target=entry+SPEC.target_rr*(entry-stop)
        if not 0<stop<entry<target:return ()
    else:
        stop=max(high,entry+atr)+0.1*atr
        target=entry-SPEC.target_rr*(stop-entry)
        if not 0<target<entry<stop:return ()
    return (ResearchSignal(symbol,"volatility_breakout",direction,decision_ms,entry,stop,target),)
