"""Capacity preflight and sampling tests."""
import pytest

from research.l2_capacity import SampleGate, StoragePlan


def test_full_rate_rejected_by_small_budget():
    plan = StoragePlan(6, 100, 96, 1024, 512 * 1024 * 1024)
    assert plan.estimated_documents == 20_736_000
    with pytest.raises(ValueError, match="budget exceeded"):
        plan.require_capacity()


def test_downsampled_plan_fits_estimated_budget():
    plan = StoragePlan(6, 10000, 96, 1024, 512 * 1024 * 1024)
    assert plan.estimated_documents == 207_360
    plan.require_capacity()


def test_sample_gate_is_independent_per_stream():
    gate = SampleGate(10000)
    assert gate.accept("binance", "SOL", 100000)
    assert not gate.accept("binance", "SOL", 105000)
    assert gate.accept("okx", "SOL", 105000)
    assert gate.accept("binance", "SOL", 110000)


def test_sample_gate_rejects_nonmonotonic_time():
    gate = SampleGate(1000)
    assert gate.accept("okx", "XRP", 1000)
    with pytest.raises(ValueError, match="nonmonotonic"):
        gate.accept("okx", "XRP", 999)
