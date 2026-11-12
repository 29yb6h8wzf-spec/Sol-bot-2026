"""Synthetic A/B harness tests; these do NOT establish historical profitability."""
from dataclasses import replace
import pytest
from signals_v2.ab import Opportunity, compare_ab, WEEK_MS
from signals_v2.oos import ChronologicalSplit, ClosedTrade, EvidenceRejected, Period

BASE = 1_800_000_000_000
DAY = 86_400_000


def fixture():
    s = ChronologicalSplit(
        Period(BASE, BASE + 20*DAY),
        Period(BASE + 21*DAY, BASE + 40*DAY),
        Period(BASE + 41*DAY, BASE + 60*DAY),
        Period(BASE + 61*DAY, BASE + 150*DAY),
        48*300_000)
    opportunities = tuple(Opportunity(f"evt-{i}", "SOLUSDT",
                          BASE + (62+i*7)*DAY) for i in range(9))
    return s, opportunities


def trade(o, gross, *, fee=.1):
    return ClosedTrade(o.symbol, "LONG", o.decision_ms,
                       o.decision_ms+300_000, gross, fee, 0, 0, o.event_id)


def evaluate(s, opportunities, old, v2, **kwargs):
    return compare_ab(s, opportunities, tuple(old), tuple(v2),
                      fee_cost_model_id="fee-v1",
                      exit_policy_id="common-v1",
                      data_snapshot_hash="synthetic-only", **kwargs)


def test_ab_is_descriptive_not_proof():
    s, grid = fixture()
    result = evaluate(s, grid, [trade(o, -.9) for o in grid],
                      [trade(o, 1.1) for o in grid], seed=3)
    assert result["status"] == "DESCRIPTIVE_ONLY"
    assert result["readiness"] == "NOT_READY"
    assert result["uplift_lower_bound_positive"]
    assert result["shared_opportunities"] == 9
    assert result["old_trade_count"] == result["v2_trade_count"] == 9


def test_ab_keeps_abstentions_as_zero():
    s, grid = fixture()
    result = evaluate(s, grid, [trade(grid[0], 1.1)],
                      [trade(grid[1], 2.1)], seed=2)
    assert result["net_uplift_total_r"] == pytest.approx(1.0)
    assert result["net_uplift_per_shared_opportunity_r"] == pytest.approx(1/9)
    assert result["old_trade_count"] == 1
    assert result["v2_trade_count"] == 1


def test_no_common_opportunity_is_rejected():
    s, grid = fixture()
    outsider = Opportunity("outside", "SOLUSDT", grid[0].decision_ms)
    with pytest.raises(EvidenceRejected, match="outside_shared"):
        evaluate(s, grid, [], [trade(outsider, 1)])


def test_duplicate_opportunities_rejected():
    s, grid = fixture()
    with pytest.raises(EvidenceRejected, match="duplicate_opportunity"):
        evaluate(s, grid + (grid[0],), [], [])


def test_missing_provenance_rejected():
    s, grid = fixture()
    with pytest.raises(EvidenceRejected, match="missing_ab_provenance"):
        compare_ab(s, grid, (), (), fee_cost_model_id="",
                   exit_policy_id="common", data_snapshot_hash="abc")


def test_future_and_boundary_opportunities_rejected():
    s, grid = fixture()
    early = Opportunity("early", "SOLUSDT", BASE + 50*DAY)
    with pytest.raises(EvidenceRejected, match="opportunity_not_in_locked_test"):
        evaluate(s, grid + (early,), [], [])


def test_deterministic_weekly_bootstrap():
    s, grid = fixture()
    old = [trade(o, .1) for o in grid[::2]]
    v2 = [trade(o, 1) for o in grid[1::2]]
    a = evaluate(s, grid, old, v2, seed=10)
    b = evaluate(s, grid, old, v2, seed=10)
    assert a["weekly_bootstrap_uplift_ci95_per_opportunity_r"] == (
        b["weekly_bootstrap_uplift_ci95_per_opportunity_r"])


def test_same_event_cannot_be_double_counted():
    s, grid = fixture()
    with pytest.raises(EvidenceRejected, match="duplicate_engine_event"):
        evaluate(s, grid, [], [trade(grid[0], 1), trade(grid[0], 2)])
