"""Leakage-safe chronological OOS gates and cost-aware evaluation for V2 research.

No live broker dependencies. Never claim profitability from in-sample results.
"""
from dataclasses import dataclass
from math import isfinite
from statistics import mean
from typing import Sequence


class EvidenceRejected(ValueError):
    pass


@dataclass(frozen=True)
class Period:
    start_ms: int
    end_ms: int

    def __post_init__(self):
        if type(self.start_ms) is not int or type(self.end_ms) is not int or self.start_ms >= self.end_ms:
            raise EvidenceRejected("invalid_period")


@dataclass(frozen=True)
class ChronologicalSplit:
    train: Period
    validation: Period
    calibration: Period
    test: Period
    embargo_ms: int

    def __post_init__(self):
        if type(self.embargo_ms) is not int or self.embargo_ms < 48 * 300_000:
            raise EvidenceRejected("embargo_below_max_holding")
        periods = (self.train, self.validation, self.calibration, self.test)
        if any(not isinstance(p, Period) for p in periods):
            raise EvidenceRejected("invalid_period")
        for a, b in zip(periods, periods[1:]):
            if a.end_ms + self.embargo_ms > b.start_ms:
                raise EvidenceRejected("overlapping_or_unpurged_split")

    def locate(self, decision_ms: int, label_end_ms: int) -> str | None:
        """Keep entire label horizon inside one partition; reject boundary crossing."""
        if type(decision_ms) is not int or type(label_end_ms) is not int or label_end_ms < decision_ms:
            raise EvidenceRejected("invalid_label_horizon")
        for name in ("train", "validation", "calibration", "test"):
            p = getattr(self, name)
            if p.start_ms <= decision_ms and label_end_ms < p.end_ms:
                return name
        return None


@dataclass(frozen=True)
class ClosedTrade:
    symbol: str
    direction: str
    decision_ms: int
    exit_ms: int
    gross_return_r: float
    fee_r: float
    slippage_r: float
    funding_r: float
    event_id: str

    def __post_init__(self):
        if self.symbol not in ("SOLUSDT", "XRPUSDT") or self.direction not in ("LONG", "SHORT"):
            raise EvidenceRejected("invalid_symbol_or_direction")
        if type(self.decision_ms) is not int or type(self.exit_ms) is not int or not self.decision_ms < self.exit_ms <= self.decision_ms + 48 * 300_000:
            raise EvidenceRejected("invalid_holding_period")
        if not self.event_id or not isinstance(self.event_id, str):
            raise EvidenceRejected("missing_event_id")
        for value in (self.gross_return_r, self.fee_r, self.slippage_r, self.funding_r):
            if type(value) not in (int, float) or not isfinite(value):
                raise EvidenceRejected("invalid_cost_or_return")
        if self.fee_r < 0 or self.slippage_r < 0:
            raise EvidenceRejected("negative_transaction_cost")

    @property
    def net_r(self) -> float:
        return self.gross_return_r - self.fee_r - self.slippage_r - self.funding_r


@dataclass(frozen=True)
class PeriodMetrics:
    count: int
    win_rate: float | None
    expectancy_r: float | None
    profit_factor: float | None
    max_drawdown_r: float | None
    total_net_r: float
    status: str


def metrics(trades: Sequence[ClosedTrade]) -> PeriodMetrics:
    if not trades:
        return PeriodMetrics(0, None, None, None, None, 0.0, "INCONCLUSIVE")
    seen = set()
    ordered = sorted(trades, key=lambda t: (t.decision_ms, t.event_id))
    for t in ordered:
        if not isinstance(t, ClosedTrade):
            raise EvidenceRejected("invalid_trade")
        if t.event_id in seen:
            raise EvidenceRejected("duplicate_economic_event")
        seen.add(t.event_id)
    returns = [t.net_r for t in ordered]
    gains = sum(max(0.0, x) for x in returns)
    losses = -sum(min(0.0, x) for x in returns)
    # Profit factor is undefined when there are no losses; do not report infinity.
    factor = gains / losses if losses > 0 else None
    equity = peak = max_dd = 0.0
    for value in returns:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return PeriodMetrics(len(returns), sum(x > 0 for x in returns) / len(returns),
                         mean(returns), factor, max_dd, sum(returns), "DESCRIPTIVE_ONLY")


def validate_locked_oos(split: ChronologicalSplit, trades: Sequence[ClosedTrade],
                        *, minimum_events: int = 200, minimum_weeks: int = 8
                        ) -> dict:
    """Evidence gate: no inference from trade count or point estimate alone.

    Requires external block-bootstrap confidence bound and fair A/B comparison
    before a READY_TO_REPLACE decision; this function cannot certify either.
    """
    if not isinstance(split, ChronologicalSplit):
        raise EvidenceRejected("missing_locked_split")
    if type(minimum_events) is not int or minimum_events < 1:
        raise EvidenceRejected("invalid_minimum_events")
    if type(minimum_weeks) is not int or minimum_weeks < 1:
        raise EvidenceRejected("invalid_minimum_weeks")
    for t in trades:
        if split.locate(t.decision_ms, t.exit_ms) != "test":
            raise EvidenceRejected("non_test_or_boundary_crossing_trade")
    result = metrics(trades)
    coverage_weeks = (split.test.end_ms - split.test.start_ms) // (7 * 24 * 3600 * 1000)
    blockers = []
    if result.count < minimum_events:
        blockers.append("insufficient_independent_oos_events")
    if coverage_weeks < minimum_weeks:
        blockers.append("insufficient_locked_test_weeks")
    if result.expectancy_r is None or result.expectancy_r <= 0:
        blockers.append("nonpositive_net_oos_expectancy")
    blockers.extend(("two_locked_oos_windows_not_verified",
                     "weekly_bootstrap_lower_bound_not_verified",
                     "fair_ab_comparison_not_verified"))
    return {"status": "INCONCLUSIVE", "blockers": blockers,
            "oos_event_count": result.count, "test_window_weeks": coverage_weeks,
            "net_expectancy_r": result.expectancy_r,
            "net_total_r": result.total_net_r}
