"""Point-in-time dynamic USDT-M research universe eligibility.

Input observations must be captured at or before decision time. This module
never calls an exchange and never authorizes orders. Missing evidence fails closed.
"""
from dataclasses import dataclass
from math import isfinite
import re

_SYMBOL_PATTERN = re.compile(r"[A-Z0-9]{2,30}USDT\Z")

MIN_PRICE_USD=0.99
MAX_PRICE_USD=150.0

@dataclass(frozen=True)
class UniverseObservation:
    symbol:str
    observed_at_ms:int
    last_price_usd:float
    quote_volume_24h_usd:float
    spread_bps:float
    bid_depth_10bps_usd:float
    ask_depth_10bps_usd:float
    min_notional_usd:float
    status:str
    contract_type:str
    quote_asset:str

@dataclass(frozen=True)
class UniverseThresholds:
    min_quote_volume_24h_usd:float=10_000_000.0
    max_spread_bps:float=10.0
    min_each_side_depth_10bps_usd:float=10_000.0
    max_observation_age_ms:int=60_000
    available_notional_usd:float=75.0

def eligibility(obs:UniverseObservation,decision_ms:int,limits:UniverseThresholds=UniverseThresholds()):
    # Untrusted historical/provider data must fail closed rather than crash a replay.
    # Configuration is also an untrusted input. NaN/negative thresholds can
    # otherwise silently disable spread, depth or staleness gates.
    if not isinstance(limits,UniverseThresholds):
        return False,"invalid_universe_thresholds"
    numeric=(limits.min_quote_volume_24h_usd,limits.max_spread_bps,
             limits.min_each_side_depth_10bps_usd,limits.available_notional_usd)
    if (any(type(v) not in (int,float) or not isfinite(v) or v<0 for v in numeric)
        or type(limits.max_observation_age_ms) is not int
        or limits.max_observation_age_ms<0):
        return False,"invalid_universe_thresholds"
    if not isinstance(obs,UniverseObservation):
        return False,"invalid_market_data"
    if any(type(v) is not int for v in (decision_ms,obs.observed_at_ms)) or decision_ms<0 or obs.observed_at_ms<0:
        return False,"invalid_market_data"
    if any(type(v) not in (int,float) for v in (
        obs.last_price_usd,obs.quote_volume_24h_usd,obs.spread_bps,
        obs.bid_depth_10bps_usd,obs.ask_depth_10bps_usd,obs.min_notional_usd)):
        return False,"invalid_market_data"
    if not isinstance(obs.symbol,str) or not isinstance(obs.quote_asset,str) or not isinstance(obs.status,str) or not isinstance(obs.contract_type,str):
        return False,"invalid_market_data"
    if obs.observed_at_ms>decision_ms or decision_ms-obs.observed_at_ms>limits.max_observation_age_ms:
        return False,"missing_point_in_time_evidence"
    if not _SYMBOL_PATTERN.fullmatch(obs.symbol) or obs.quote_asset!="USDT" or obs.status!="TRADING" or obs.contract_type!="PERPETUAL":
        return False,"unsupported_market"
    values=(obs.last_price_usd,obs.quote_volume_24h_usd,obs.spread_bps,obs.bid_depth_10bps_usd,obs.ask_depth_10bps_usd,obs.min_notional_usd)
    if not all(isfinite(v) for v in values) or any(v<0 for v in values):
        return False,"invalid_market_data"
    if not MIN_PRICE_USD<=obs.last_price_usd<=MAX_PRICE_USD:
        return False,"outside_price_range"
    if obs.quote_volume_24h_usd<limits.min_quote_volume_24h_usd:
        return False,"insufficient_volume"
    if obs.spread_bps>limits.max_spread_bps:
        return False,"spread_too_wide"
    if min(obs.bid_depth_10bps_usd,obs.ask_depth_10bps_usd)<limits.min_each_side_depth_10bps_usd:
        return False,"insufficient_depth"
    if obs.min_notional_usd>limits.available_notional_usd:
        return False,"min_notional_exceeds_allocation"
    return True,"eligible"

def select_universe(observations,decision_ms,limits=UniverseThresholds()):
    # Validate configuration even when a replay has no observations. An empty
    # batch must not silently certify an invalid research configuration.
    if not isinstance(limits, UniverseThresholds):
        raise ValueError("invalid_universe_thresholds")
    numeric = (limits.min_quote_volume_24h_usd, limits.max_spread_bps,
               limits.min_each_side_depth_10bps_usd, limits.available_notional_usd)
    if (any(type(v) not in (int, float) or not isfinite(v) or v < 0 for v in numeric)
            or type(limits.max_observation_age_ms) is not int
            or limits.max_observation_age_ms < 0):
        raise ValueError("invalid_universe_thresholds")
    if type(decision_ms) is not int or decision_ms < 0:
        raise ValueError("invalid_decision_timestamp")
    if observations is None or isinstance(observations,(str,bytes,dict)):
        raise ValueError("invalid_universe_observations")
    try:
        iterator = iter(observations)
    except TypeError as exc:
        raise ValueError("invalid_universe_observations") from exc
    accepted=[];reasons={}
    for obs in iterator:
        if not isinstance(obs,UniverseObservation) or not isinstance(obs.symbol,str) or not obs.symbol:
            raise ValueError("invalid_universe_observation_identity")
        if obs.symbol in reasons:
            raise ValueError("duplicate_universe_observation")
        ok,reason=eligibility(obs,decision_ms,limits)
        reasons[obs.symbol]=reason
        if ok:accepted.append(obs.symbol)
    return tuple(sorted(set(accepted))),reasons
