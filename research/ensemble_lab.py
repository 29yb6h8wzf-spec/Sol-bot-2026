"""Offline multi-engine research scoring: Quant, ML, and quantum-inspired allocation.

No claims of predictive validity or quantum advantage. No execution API.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class Candidate:
    symbol: str
    quant_score: float
    ml_probability: float
    estimated_cost_fraction: float
    max_loss_usdt: float

    def __post_init__(self) -> None:
        values = (self.quant_score, self.ml_probability, self.estimated_cost_fraction, self.max_loss_usdt)
        if not all(isfinite(v) for v in values):
            raise ValueError("nonfinite candidate")
        if not 0 <= self.quant_score <= 1 or not 0 <= self.ml_probability <= 1:
            raise ValueError("scores must be in [0, 1]")
        if self.estimated_cost_fraction < 0 or self.max_loss_usdt < 0:
            raise ValueError("negative cost or risk")


def ensemble_score(candidate: Candidate, *, quant_weight: float = 0.5) -> float:
    """A research baseline, not a calibrated success probability."""
    if not 0 <= quant_weight <= 1:
        raise ValueError("invalid ensemble weight")
    return quant_weight * candidate.quant_score + (1 - quant_weight) * candidate.ml_probability


def classical_allocation(
    candidates: Sequence[Candidate], *, risk_budget_usdt: float, max_positions: int = 2
) -> tuple[str, ...]:
    """Exact small-universe subset search under additive stop-risk budget.

    Serves as a reproducible baseline for future quantum optimization experiments.
    """
    if not isfinite(risk_budget_usdt) or risk_budget_usdt < 0 or max_positions < 0:
        raise ValueError("invalid risk budget")
    if len({c.symbol for c in candidates}) != len(candidates):
        raise ValueError("duplicate symbols")
    if len(candidates) > 20:
        raise ValueError("exact search limited to 20 candidates")
    best_score = 0.0
    best: tuple[str, ...] = ()
    for mask in range(1 << len(candidates)):
        chosen = [c for i, c in enumerate(candidates) if mask & (1 << i)]
        if len(chosen) > max_positions:
            continue
        if sum(c.max_loss_usdt for c in chosen) > risk_budget_usdt + 1e-9:
            continue
        score = sum(ensemble_score(c) - c.estimated_cost_fraction for c in chosen)
        symbols = tuple(sorted(c.symbol for c in chosen))
        if score > best_score + 1e-12 or (abs(score - best_score) < 1e-12 and symbols < best):
            best_score, best = score, symbols
    return best
