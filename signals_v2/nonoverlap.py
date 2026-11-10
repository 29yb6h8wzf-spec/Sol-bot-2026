"""Research-only non-overlap gate for candidate hypotheses.

Selects at most one candidate per symbol within a fixed holding horizon.
This is a conservative diagnostic filter, NOT an execution simulator:
actual exit times and portfolio cross-symbol constraints remain separate.
"""
from collections import defaultdict
from signals_v2.hybrid import Hypothesis


def select_nonoverlapping(proposals, *, holding_ms=14_400_000):
    if not isinstance(holding_ms, int) or isinstance(holding_ms, bool) or holding_ms <= 0:
        raise ValueError("invalid_holding_horizon")
    ordered = sorted(proposals, key=lambda p: (p.decision_ms, p.symbol, p.specialist, p.direction))
    last_end = defaultdict(lambda: -1)
    chosen = []
    seen = set()
    for p in ordered:
        if not isinstance(p, Hypothesis) or not p.research_only or p.execution_authorized:
            raise ValueError("research_only_hypothesis_required")
        if p.symbol not in ("SOLUSDT", "XRPUSDT") or p.direction not in ("LONG", "SHORT"):
            raise ValueError("unsupported_hypothesis")
        if not isinstance(p.decision_ms, int) or p.decision_ms < 0:
            raise ValueError("invalid_decision_time")
        key = (p.symbol, p.decision_ms, p.specialist, p.direction)
        if key in seen:
            raise ValueError("duplicate_hypothesis")
        seen.add(key)
        if p.decision_ms < last_end[p.symbol]:
            continue
        chosen.append(p)
        last_end[p.symbol] = p.decision_ms + holding_ms
    return tuple(chosen)
