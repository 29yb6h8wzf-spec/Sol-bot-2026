"""Research-only deterministic market regime baseline for Signals V2.

Thresholds below are HYPOTHESES, not tuned parameters or evidence of edge.
The regime detector can abstain. No order signals or broker integration.
"""
from dataclasses import dataclass
from statistics import median
from signals_v2.contracts import MarketSnapshot, DataRejected
from signals_v2.structure import structure


@dataclass(frozen=True)
class RegimeObservation:
    regime: str
    reason: str
    atr_ratio: float
    compression_ratio: float
    available_at_ms: int
    research_only: bool = True


def _true_ranges(bars):
    result = []
    for previous, current in zip(bars, bars[1:]):
        result.append(max(current.high - current.low,
                          abs(current.high - previous.close),
                          abs(current.low - previous.close)))
    return result


def classify(snapshot: MarketSnapshot) -> RegimeObservation:
    """Evaluate only closed 5m candles and data already available at decision."""
    if not isinstance(snapshot, MarketSnapshot):
        raise DataRejected("invalid_market_snapshot")
    snapshot.validate(min_five=64, min_one=10)
    bars = snapshot.five_minute
    ranges = _true_ranges(bars)
    recent_atr = sum(ranges[-14:]) / 14
    baseline_atr = median(ranges[-63:-14])
    if baseline_atr <= 0:
        return RegimeObservation("UNKNOWN", "zero_baseline_volatility", 0, 0,
                                 bars[-1].close_ms(300_000))
    atr_ratio = recent_atr / baseline_atr
    # A compression score compares the current 12-bar high-low width with
    # widths of *past* nonoverlapping 12-bar windows.
    width = lambda group: max(b.high for b in group) - min(b.low for b in group)
    historical = [width(bars[-60:-48]), width(bars[-48:-36]),
                  width(bars[-36:-24]), width(bars[-24:-12])]
    historical_median = median(historical)
    compression = (width(bars[-12:]) / historical_median
                   if historical_median > 0 else float("inf"))
    observation = structure(bars)
    regime, reason = "UNKNOWN", "no_confirmed_regime"
    if atr_ratio >= 1.8:
        regime, reason = "HIGH_VOLATILITY", "atr_expansion"
    elif observation.event in ("BOS_UP", "BOS_DOWN", "CHOCH_UP", "CHOCH_DOWN"):
        regime, reason = "BREAKOUT_TRANSITION", observation.event
    elif compression <= 0.7:
        regime, reason = "RANGE_COMPRESSION", "compressed_12_bar_range"
    elif observation.trend in ("UP", "DOWN"):
        regime, reason = "TREND", "confirmed_structure_" + observation.trend
    return RegimeObservation(regime, reason, atr_ratio, compression,
                             bars[-1].close_ms(300_000))
