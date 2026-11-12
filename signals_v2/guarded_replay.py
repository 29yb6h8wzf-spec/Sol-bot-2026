"""Research replay adapter that enforces historical quality exclusions before scoring.

The ordinary replay() API does not know about missing/mismatched history.
Call this adapter for all archived-data evaluation. No exchange connectivity.
"""
from signals_v2.contracts import DataRejected,FIVE_MINUTES_MS
from signals_v2.replay import replay
from signals_v2.backtest_exclusion_gate import eligible

def guarded_replay(proposal, feature_bars, future_bars, intervals, **kwargs):
    if not feature_bars or not future_bars:
        raise DataRejected("missing_feature_or_future_bars")
    if not isinstance(feature_bars,tuple) or not isinstance(future_bars,tuple):
        raise DataRejected("expected_immutable_candle_tuples")
    symbol=proposal.symbol
    if any(b.open_ms - a.open_ms!=FIVE_MINUTES_MS for a,b in zip(feature_bars,feature_bars[1:])):
        raise DataRejected("noncontinuous_feature_history")
    if any(b.open_ms - a.open_ms!=FIVE_MINUTES_MS for a,b in zip(future_bars,future_bars[1:])):
        raise DataRejected("noncontinuous_future_history")
    if feature_bars[-1].open_ms+FIVE_MINUTES_MS!=future_bars[0].open_ms:
        raise DataRejected("feature_future_boundary_gap")
    # Conservative full requested holding horizon, not just observed stop/target.
    max_bars=kwargs.get("max_bars",48)
    if type(max_bars)!=int or not 1<=max_bars<=48:
        raise DataRejected("invalid_holding_horizon")
    if len(future_bars)!=max_bars:
        raise DataRejected("incomplete_full_horizon")
    ok,reason=eligible(intervals,symbol,feature_bars[0].open_ms,
        future_bars[0].open_ms,future_bars[-1].open_ms+FIVE_MINUTES_MS)
    if not ok:raise DataRejected("excluded_market_history:"+reason["reason"])
    return replay(proposal,future_bars,**kwargs)
