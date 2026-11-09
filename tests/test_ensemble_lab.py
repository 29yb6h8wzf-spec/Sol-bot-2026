"""Offline tests for Quant/ML/quantum-inspired optimization baseline."""
import pytest

from research.ensemble_lab import Candidate, classical_allocation, ensemble_score


def candidate(symbol, score, risk, cost=0):
    return Candidate(symbol, score, score, cost, risk)


def test_ensemble_is_not_a_probability_claim():
    c = Candidate("SOL", 0.8, 0.4, 0.001, 0.5)
    assert ensemble_score(c) == pytest.approx(0.6)


def test_exact_allocation_respects_risk_and_positions():
    cs = [candidate("SOL", 0.9, 0.75), candidate("XRP", 0.8, 0.75),
          candidate("ETH", 0.4, 0.3)]
    assert classical_allocation(cs, risk_budget_usdt=1.5, max_positions=2) == ("SOL", "XRP")


def test_no_trade_if_budget_too_small():
    assert classical_allocation([candidate("SOL", 0.9, 1.0)], risk_budget_usdt=0.5) == ()


def test_costs_can_make_no_trade_optimal():
    assert classical_allocation([candidate("SOL", 0.2, 0.5, 0.3)], risk_budget_usdt=1.5) == ()


def test_invalid_inputs_fail_closed():
    with pytest.raises(ValueError):
        Candidate("SOL", float("nan"), 0.5, 0, 0.5)
    with pytest.raises(ValueError):
        classical_allocation([candidate("SOL", 0.9, 0.5)] * 2, risk_budget_usdt=1.5)
