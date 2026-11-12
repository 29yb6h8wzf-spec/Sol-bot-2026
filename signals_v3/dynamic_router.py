"""Dynamic research routing with mandatory point-in-time eligibility evidence.

Existing SOL/XRP pilot router remains unchanged until full archive coverage and
native 1m replay are validated. No execution access.
"""
from signals_v2.contracts import DataRejected
from signals_v3.dynamic_universe import eligibility
from signals_v3.spec import SPEC
from signals_v3.trend_pullback import trend_pullback
from signals_v3.volatility_breakout import volatility_breakout
from signals_v3.liquidity_reversal import liquidity_reversal

def candidates_dynamic(observation,five,one,decision_ms):
    SPEC.validate()
    eligible,reason=eligibility(observation,decision_ms)
    if not eligible:raise DataRejected("dynamic_universe:"+reason)
    symbol=observation.symbol
    result=[]
    for strategy in (trend_pullback,volatility_breakout,liquidity_reversal):
        result.extend(strategy(symbol,five,one,decision_ms))
    if any(not s.research_only or s.execution_authorized for s in result):
        raise DataRejected("executable_signal_forbidden")
    if len({s.direction for s in result})>1:return ()
    return tuple(result)
