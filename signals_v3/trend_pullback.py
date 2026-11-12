"""Causal, research-only V3 trend-pullback hypothesis.

The first V3 candidate is intentionally strict: 1m trigger with 5m trend
context. Higher-timeframe trend filters and point-in-time universe follow.
"""
from dataclasses import dataclass
from statistics import mean
from signals_v2.contracts import Candle,DataRejected,FIVE_MINUTES_MS,MINUTE_MS
from signals_v2.features import ema
from signals_v3.spec import SPEC

@dataclass(frozen=True)
class ResearchSignal:
    symbol: str
    strategy: str
    direction: str
    decision_ms: int
    entry_reference: float
    stop_reference: float
    target_reference: float
    research_only: bool = True
    execution_authorized: bool = False

def trend_pullback(symbol: str, five: tuple[Candle,...], one: tuple[Candle,...], decision_ms: int):
    SPEC.validate()
    if not isinstance(five,tuple) or len(five)<64 or not isinstance(one,tuple) or len(one)<30:
        raise DataRejected("insufficient_v3_history")
    for bars,period in ((five,FIVE_MINUTES_MS),(one,MINUTE_MS)):
        for bar in bars:bar.validate(period,decision_ms)
        if any(b.open_ms-a.open_ms!=period for a,b in zip(bars,bars[1:])):
            raise DataRejected("missing_or_duplicate_bar")
        if decision_ms-bars[-1].close_ms(period)>period:
            raise DataRejected("stale_v3_history")
    if one[-1].close_ms(MINUTE_MS)<five[-1].close_ms(FIVE_MINUTES_MS):
        raise DataRejected("one_minute_precedes_five_minute")
    closes=tuple(x.close for x in five)
    fast=ema(closes,9);slow=ema(closes,21)
    prev_fast=ema(closes[:-1],9)
    one_closes=tuple(x.close for x in one)
    micro_fast=ema(one_closes,9)
    # Require recent 1m pullback into its own fast average and reclaim.
    last=one[-1];previous=one[-2]
    atr=mean(max(c.high-c.low,abs(c.high-p.close),abs(c.low-p.close))
             for p,c in zip(five[-15:-1],five[-14:]))
    if atr<=0:raise DataRejected("zero_atr")
    volume_base=mean(x.volume for x in one[-21:-1])
    if volume_base<=0:raise DataRejected("zero_volume_baseline")
    if last.volume/volume_base<1.1:return ()
    direction=None
    if fast>slow and fast>=prev_fast and last.close>micro_fast and previous.low<=micro_fast and last.close>last.open:
        direction="LONG"
    elif fast<slow and fast<=prev_fast and last.close<micro_fast and previous.high>=micro_fast and last.close<last.open:
        direction="SHORT"
    if direction is None:return ()
    entry=last.close
    if direction=="LONG":
        stop=min(x.low for x in one[-6:])-0.1*atr
        target=entry+SPEC.target_rr*(entry-stop)
        if not 0<stop<entry<target:return ()
    else:
        stop=max(x.high for x in one[-6:])+0.1*atr
        target=entry-SPEC.target_rr*(stop-entry)
        if not 0<target<entry<stop:return ()
    return (ResearchSignal(symbol,"trend_pullback",direction,decision_ms,entry,stop,target),)
