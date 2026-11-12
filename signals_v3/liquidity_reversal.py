"""Research-only liquidity sweep and reclaim. Closed 1m candles only."""
from statistics import mean
from signals_v2.contracts import Candle,DataRejected,MINUTE_MS,FIVE_MINUTES_MS
from signals_v3.spec import SPEC
from signals_v3.trend_pullback import ResearchSignal

def liquidity_reversal(symbol: str,five: tuple[Candle,...],one: tuple[Candle,...],decision_ms: int):
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
    # Levels are formed BEFORE the sweep candle. No trigger-bar leakage.
    base=one[-31:-1]
    low=min(b.low for b in base);high=max(b.high for b in base)
    last=one[-1]
    volume_base=mean(b.volume for b in base)
    if volume_base<=0:raise DataRejected("zero_volume_baseline")
    if last.volume/volume_base<1.2:return ()
    # Reclaim into the old range with a candle in the reversal direction.
    long=last.low<low and low<last.close<high and last.close>last.open
    short=last.high>high and low<last.close<high and last.close<last.open
    if not long and not short:return ()
    atr=mean(max(c.high-c.low,abs(c.high-p.close),abs(c.low-p.close))
             for p,c in zip(five[-15:-1],five[-14:]))
    if atr<=0:raise DataRejected("zero_atr")
    entry=last.close
    if long:
        stop=min(last.low,low)-0.1*atr
        target=entry+SPEC.target_rr*(entry-stop)
        if not 0<stop<entry<target:return ()
        direction="LONG"
    else:
        stop=max(last.high,high)+0.1*atr
        target=entry-SPEC.target_rr*(stop-entry)
        if not 0<target<entry<stop:return ()
        direction="SHORT"
    return (ResearchSignal(symbol,"liquidity_reversal",direction,decision_ms,entry,stop,target),)
