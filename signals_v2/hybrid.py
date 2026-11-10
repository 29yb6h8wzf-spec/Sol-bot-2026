"""Three competing research-only setups under a single regime-aware router.

These rules are uncalibrated hypotheses. Their outputs are *not* executable
orders, nor proof of expected profit. No ML probability is fabricated.
"""
from dataclasses import dataclass
from signals_v2.contracts import MarketSnapshot, DataRejected
from signals_v2.features import features
from signals_v2.regime import classify
from signals_v2.structure import structure


@dataclass(frozen=True)
class Hypothesis:
    schema_version: str
    symbol: str
    direction: str
    specialist: str
    regime: str
    decision_ms: int
    entry_reference: float
    stop_reference: float
    target_reference: float
    valid_until_ms: int
    quality_score: None = None
    calibrated_probability: None = None
    execution_authorized: bool = False
    research_only: bool = True


def candidates(snapshot: MarketSnapshot) -> tuple[Hypothesis, ...]:
    snapshot.validate(min_five=64, min_one=10)
    bars = snapshot.five_minute
    reg = classify(snapshot)
    s = structure(bars)
    f = features(bars)
    if reg.regime in ("UNKNOWN", "RANGE_COMPRESSION"):
        return ()
    # 1m is a confirmation of the completed 5m candle, never future data.
    one = snapshot.one_minute[-1]
    price = bars[-1].close
    one_confirm_up = one.close >= one.open
    one_confirm_down = one.close <= one.open
    proposals = []
    if reg.regime == "TREND":
        if s.trend == "UP" and f.ema_fast > f.ema_slow and f.momentum_6 > 0 and one_confirm_up:
            proposals.append(("trend_continuation", "LONG"))
        if s.trend == "DOWN" and f.ema_fast < f.ema_slow and f.momentum_6 < 0 and one_confirm_down:
            proposals.append(("trend_continuation", "SHORT"))
    if reg.regime in ("BREAKOUT_TRANSITION", "HIGH_VOLATILITY"):
        if s.event in ("BOS_UP", "CHOCH_UP") and f.relative_volume >= 1.1 and one_confirm_up:
            proposals.append(("breakout_expansion", "LONG"))
        if s.event in ("BOS_DOWN", "CHOCH_DOWN") and f.relative_volume >= 1.1 and one_confirm_down:
            proposals.append(("breakout_expansion", "SHORT"))
    if reg.regime in ("HIGH_VOLATILITY", "BREAKOUT_TRANSITION"):
        if s.event == "SWEEP_LOW" and one_confirm_up:
            proposals.append(("liquidity_reversal", "LONG"))
        if s.event == "SWEEP_HIGH" and one_confirm_down:
            proposals.append(("liquidity_reversal", "SHORT"))
    result = []
    for specialist, direction in proposals:
        # Strict research-only references: not an executable fill, SL or TP.
        if direction == "LONG":
            support = s.latest_support
            structural_stop = min(support, price - f.atr14) if support else price - f.atr14
            stop = structural_stop - 0.1 * f.atr14
            target = price + 2 * (price - stop)
        else:
            resistance = s.latest_resistance
            structural_stop = max(resistance, price + f.atr14) if resistance else price + f.atr14
            stop = structural_stop + 0.1 * f.atr14
            target = price - 2 * (stop - price)
        if stop <= 0 or target <= 0:
            continue
        if direction == "LONG" and not stop < price < target:
            raise DataRejected("invalid_long_geometry")
        if direction == "SHORT" and not target < price < stop:
            raise DataRejected("invalid_short_geometry")
        result.append(Hypothesis(
            "signals.v2.research.1", snapshot.symbol, direction, specialist,
            reg.regime, snapshot.decision_ms, price, stop, target,
            snapshot.decision_ms + 600_000))
    return tuple(result)
