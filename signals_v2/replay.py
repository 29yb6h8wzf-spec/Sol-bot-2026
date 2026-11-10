"""Conservative offline event-level replay for Signals V2 research.

This does NOT model an exchange order. A proposal's close is a reference,
so entry is modeled at the NEXT 5m open with explicit adverse costs.
"""
from dataclasses import dataclass
from math import isfinite
from signals_v2.contracts import Candle, DataRejected, FIVE_MINUTES_MS
from signals_v2.hybrid import Hypothesis


@dataclass(frozen=True)
class ReplayResult:
    exit_reason: str
    bars_held: int
    entry_fill: float
    exit_fill: float
    net_r: float
    fee_r: float
    funding_r: float
    research_only: bool = True


def replay(proposal: Hypothesis, future_bars: tuple[Candle, ...], *,
           fee_rate_per_side: float = 0.0005,
           slippage_rate_per_side: float = 0.0002,
           funding_rate_total: float = 0.0,
           max_bars: int = 48) -> ReplayResult:
    if not isinstance(proposal, Hypothesis) or not proposal.research_only or proposal.execution_authorized:
        raise DataRejected("not_research_hypothesis")
    if proposal.direction not in ("LONG", "SHORT"):
        raise DataRejected("invalid_direction")
    if type(max_bars) is not int or not 1 <= max_bars <= 48:
        raise DataRejected("invalid_horizon")
    costs = (fee_rate_per_side, slippage_rate_per_side, funding_rate_total)
    if any(not isinstance(v, (int, float)) or not isfinite(v) for v in costs):
        raise DataRejected("invalid_costs")
    if min(fee_rate_per_side, slippage_rate_per_side) < 0:
        raise DataRejected("negative_cost")
    if not future_bars or len(future_bars) > max_bars:
        raise DataRejected("invalid_future_window")
    if future_bars[0].open_ms < proposal.decision_ms:
        raise DataRejected("future_bar_precedes_decision")
    if future_bars[0].open_ms > proposal.valid_until_ms:
        raise DataRejected("expired_entry")
    if any(b.open_ms - a.open_ms != FIVE_MINUTES_MS
           for a, b in zip(future_bars, future_bars[1:])):
        raise DataRejected("missing_future_bar")
    for bar in future_bars:
        bar.validate(FIVE_MINUTES_MS, bar.available_at_ms)
    side = 1 if proposal.direction == "LONG" else -1
    entry = future_bars[0].open * (1 + side * slippage_rate_per_side)
    stop, target = proposal.stop_reference, proposal.target_reference
    if side == 1 and not stop < entry < target:
        raise DataRejected("invalid_long_levels_at_fill")
    if side == -1 and not target < entry < stop:
        raise DataRejected("invalid_short_levels_at_fill")
    risk = abs(entry - stop)
    if risk <= 0:
        raise DataRejected("zero_risk")
    reason, exit_ref, held = "TIMEOUT", future_bars[-1].close, len(future_bars)
    for i, bar in enumerate(future_bars, 1):
        stop_hit = bar.low <= stop if side == 1 else bar.high >= stop
        target_hit = bar.high >= target if side == 1 else bar.low <= target
        # Conservative on same-candle ambiguity: stop always wins.
        if stop_hit:
            reason, exit_ref, held = "STOP", min(stop, bar.open) if side == 1 else max(stop, bar.open), i
            break
        if target_hit:
            reason, exit_ref, held = "TARGET", target, i
            break
    exit_fill = exit_ref * (1 - side * slippage_rate_per_side)
    gross_r = side * (exit_fill - entry) / risk
    fee_r = fee_rate_per_side * (entry + exit_fill) / risk
    # Positive funding means long pays and short receives; signed value
    # is cumulative across the actual hold, not extrapolated per bar.
    funding_r = side * funding_rate_total * entry / risk
    return ReplayResult(reason, held, entry, exit_fill,
                        gross_r - fee_r - funding_r, fee_r, funding_r)
