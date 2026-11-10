"""Fair research-only A/B evaluation on a shared, pre-registered opportunity grid.

No broker calls. A missing trade on an opportunity is a zero return, not a
deleted observation. Weekly bootstrap preserves within-week correlation.
Results are descriptive until real provenance and locked OOS are verified.
"""
from dataclasses import dataclass
from math import isfinite
from random import Random
from statistics import mean
from signals_v2.oos import ClosedTrade, ChronologicalSplit, EvidenceRejected, metrics

WEEK_MS = 7 * 86_400_000


@dataclass(frozen=True)
class Opportunity:
    """Same market decision offered to BOTH engines, even when one abstains."""
    event_id: str
    symbol: str
    decision_ms: int

    def __post_init__(self):
        if not isinstance(self.event_id, str) or not self.event_id:
            raise EvidenceRejected("invalid_opportunity_id")
        if self.symbol not in ("SOLUSDT", "XRPUSDT"):
            raise EvidenceRejected("invalid_opportunity_symbol")
        if type(self.decision_ms) is not int or self.decision_ms < 0:
            raise EvidenceRejected("invalid_opportunity_time")


def _index(trades, opportunities, split):
    lookup = {(o.event_id, o.symbol, o.decision_ms): o for o in opportunities}
    found = {}
    for t in trades:
        if not isinstance(t, ClosedTrade):
            raise EvidenceRejected("invalid_trade")
        if split.locate(t.decision_ms, t.exit_ms) != "test":
            raise EvidenceRejected("trade_not_in_locked_test")
        key = (t.event_id, t.symbol, t.decision_ms)
        if key not in lookup:
            raise EvidenceRejected("trade_outside_shared_opportunity_grid")
        if key in found:
            raise EvidenceRejected("duplicate_engine_event")
        found[key] = t
    return found


def compare_ab(split: ChronologicalSplit, opportunities: tuple[Opportunity, ...],
               old: tuple[ClosedTrade, ...], v2: tuple[ClosedTrade, ...],
               *, fee_cost_model_id: str, exit_policy_id: str,
               data_snapshot_hash: str, bootstrap_iterations: int = 2000,
               seed: int = 20261110) -> dict:
    """Paired net-R uplift; zero-return abstentions included in common denominator.

    The result is NOT proof of profitability: identical historical market data,
    identical exit assumptions, risk exposure, data provenance and independent
    OOS validation must be verified separately before a readiness decision.
    """
    if not isinstance(split, ChronologicalSplit):
        raise EvidenceRejected("missing_locked_split")
    for value in (fee_cost_model_id, exit_policy_id, data_snapshot_hash):
        if not isinstance(value, str) or not value.strip():
            raise EvidenceRejected("missing_ab_provenance")
    if type(bootstrap_iterations) is not int or not 200 <= bootstrap_iterations <= 20000:
        raise EvidenceRejected("invalid_bootstrap_iterations")
    if type(seed) is not int:
        raise EvidenceRejected("invalid_seed")
    if not isinstance(opportunities, tuple) or not opportunities:
        raise EvidenceRejected("empty_opportunity_grid")
    keys = []
    for o in opportunities:
        if not isinstance(o, Opportunity):
            raise EvidenceRejected("invalid_opportunity")
        if split.locate(o.decision_ms, o.decision_ms + 48*300_000) != "test":
            raise EvidenceRejected("opportunity_not_in_locked_test")
        key = (o.event_id, o.symbol, o.decision_ms)
        if key in keys:
            raise EvidenceRejected("duplicate_opportunity")
        keys.append(key)
    old_by = _index(old, opportunities, split)
    v2_by = _index(v2, opportunities, split)
    weekly = {}
    for key in keys:
        week = (key[2] - split.test.start_ms) // WEEK_MS
        weekly.setdefault(week, []).append(
            (old_by[key].net_r if key in old_by else 0.0,
             v2_by[key].net_r if key in v2_by else 0.0))
    # Bootstrap *weeks*, not individual trades; keep event count weights.
    blocks = list(weekly.values())
    rng = Random(seed)
    boot = []
    for _ in range(bootstrap_iterations):
        sample = [blocks[rng.randrange(len(blocks))] for _ in blocks]
        differences = [new - previous for block in sample for previous, new in block]
        boot.append(mean(differences))
    boot.sort()
    lower = boot[int(.025 * len(boot))]
    upper = boot[min(len(boot)-1, int(.975 * len(boot)))]
    old_metrics = metrics(old)
    v2_metrics = metrics(v2)
    delta = sum(t.net_r for t in v2) - sum(t.net_r for t in old)
    return {
        "status": "DESCRIPTIVE_ONLY",
        "readiness": "NOT_READY",
        "shared_opportunities": len(keys),
        "observed_weeks": len(blocks),
        "old_trade_count": old_metrics.count,
        "v2_trade_count": v2_metrics.count,
        "old_net_expectancy_per_trade_r": old_metrics.expectancy_r,
        "v2_net_expectancy_per_trade_r": v2_metrics.expectancy_r,
        "old_win_rate": old_metrics.win_rate,
        "v2_win_rate": v2_metrics.win_rate,
        "old_profit_factor": old_metrics.profit_factor,
        "v2_profit_factor": v2_metrics.profit_factor,
        "old_max_drawdown_r": old_metrics.max_drawdown_r,
        "v2_max_drawdown_r": v2_metrics.max_drawdown_r,
        "net_uplift_total_r": delta,
        "net_uplift_per_shared_opportunity_r": delta / len(keys),
        "weekly_bootstrap_uplift_ci95_per_opportunity_r": (lower, upper),
        "uplift_lower_bound_positive": lower > 0,
        "cost_model_id": fee_cost_model_id,
        "exit_policy_id": exit_policy_id,
        "data_snapshot_hash": data_snapshot_hash,
        "blockers": ["market_data_provenance_not_independently_verified",
                     "matched_exposure_and_exit_execution_not_verified",
                     "two_locked_oos_periods_not_verified",
                     "scientific_profitability_not_proven"],
    }
