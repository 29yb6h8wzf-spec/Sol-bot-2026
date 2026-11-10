"""Research OOS evidence tests: no exchange connection or invented market data."""
import pytest
from signals_v2.oos import (
    Period, ChronologicalSplit, ClosedTrade, EvidenceRejected, metrics,
    validate_locked_oos,
)

DAY = 86_400_000
BASE = 1_800_000_000_000


def split():
    return ChronologicalSplit(
        Period(BASE, BASE + 30*DAY),
        Period(BASE + 31*DAY, BASE + 50*DAY),
        Period(BASE + 51*DAY, BASE + 70*DAY),
        Period(BASE + 71*DAY, BASE + 141*DAY),
        48*300_000,
    )


def trade(i, gross=1.0, *, fee=.08, slippage=.05, funding=.01):
    decision = BASE + (72+i)*DAY
    return ClosedTrade("SOLUSDT", "LONG", decision, decision + 300_000,
                       gross, fee, slippage, funding, f"event-{i}")


def test_rejects_unpurged_splits():
    with pytest.raises(EvidenceRejected, match="overlapping_or_unpurged"):
        ChronologicalSplit(Period(BASE, BASE+DAY),
                           Period(BASE+DAY, BASE+2*DAY),
                           Period(BASE+3*DAY, BASE+4*DAY),
                           Period(BASE+5*DAY, BASE+6*DAY),
                           48*300_000)


def test_rejects_short_embargo():
    with pytest.raises(EvidenceRejected, match="embargo_below"):
        ChronologicalSplit(Period(BASE, BASE+DAY),
                           Period(BASE+2*DAY, BASE+3*DAY),
                           Period(BASE+4*DAY, BASE+5*DAY),
                           Period(BASE+6*DAY, BASE+7*DAY), 1)


def test_label_must_mature_inside_split():
    s = split()
    assert s.locate(BASE+72*DAY, BASE+72*DAY+300_000) == "test"
    assert s.locate(s.test.end_ms-300_000, s.test.end_ms) is None


def test_costs_are_deducted_from_gross_r():
    t = trade(0)
    assert t.net_r == pytest.approx(.86)
    m = metrics((t, trade(1, -1)))
    assert m.count == 2
    assert m.win_rate == .5
    assert m.expectancy_r == pytest.approx(-.14)
    assert m.max_drawdown_r == pytest.approx(1.14)


def test_duplicate_event_rejected():
    with pytest.raises(EvidenceRejected, match="duplicate_economic_event"):
        metrics((trade(0), trade(0)))


def test_negative_fee_rejected():
    with pytest.raises(EvidenceRejected, match="negative_transaction_cost"):
        trade(0, fee=-1)


def test_holding_horizon_rejected():
    with pytest.raises(EvidenceRejected, match="invalid_holding_period"):
        ClosedTrade("XRPUSDT", "SHORT", BASE, BASE+49*300_000,
                    1, .1, .1, 0, "too-long")


def test_positive_synthetic_trades_are_not_proof():
    # Synthetic numbers test guardrails, not historical profitability.
    s = split()
    ts = tuple(trade(i % 60, gross=2) for i in range(200))
    # Reused event IDs are not independent.
    with pytest.raises(EvidenceRejected, match="duplicate_economic_event"):
        validate_locked_oos(s, ts)
    unique = tuple(ClosedTrade("SOLUSDT", "LONG",
                               BASE+72*DAY+i*300_000,
                               BASE+72*DAY+(i+1)*300_000,
                               2, .08, .05, .01, f"unique-{i}")
                   for i in range(200))
    result = validate_locked_oos(s, unique)
    assert result["status"] == "INCONCLUSIVE"
    assert "weekly_bootstrap_lower_bound_not_verified" in result["blockers"]
    assert "fair_ab_comparison_not_verified" in result["blockers"]


def test_rejects_in_sample_trade():
    with pytest.raises(EvidenceRejected, match="non_test"):
        validate_locked_oos(split(), (
            ClosedTrade("XRPUSDT", "SHORT", BASE+DAY, BASE+DAY+300_000,
                        1, .1, .1, 0, "train"),
        ))


def test_empty_oos_is_inconclusive():
    result = validate_locked_oos(split(), ())
    assert result["status"] == "INCONCLUSIVE"
    assert result["oos_event_count"] == 0
