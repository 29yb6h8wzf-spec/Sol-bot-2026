"""Fail-closed research-only V3 candidate aggregator. No execution routing."""
from signals_v2.contracts import DataRejected
from signals_v3.spec import SPEC
from signals_v3.trend_pullback import trend_pullback
from signals_v3.volatility_breakout import volatility_breakout
from signals_v3.liquidity_reversal import liquidity_reversal

def candidates(symbol,five,one,decision_ms):
    SPEC.validate()
    if symbol not in ("SOLUSDT","XRPUSDT"):
        # Dynamic universe must not bypass point-in-time eligibility.
        raise DataRejected("dynamic_universe_not_yet_verified")
    result=[]
    for specialist in (trend_pullback,volatility_breakout,liquidity_reversal):
        result.extend(specialist(symbol,five,one,decision_ms))
    if any(not s.research_only or s.execution_authorized for s in result):
        raise DataRejected("executable_signal_forbidden")
    # Conflicting signals mean no trade, not an arbitrary priority choice.
    if len({s.direction for s in result})>1:return ()
    return tuple(result)
