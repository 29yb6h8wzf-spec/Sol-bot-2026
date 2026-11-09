"""Readiness gates fail closed even when only some evidence is present."""
from tools.live_readiness_gate import gate


def test_missing_evidence_blocks():
    result = gate({})
    assert not result["ready_for_live_review"]
    assert not result["live_armed"]
    assert len(result["missing"]) == 5


def test_partial_evidence_blocks():
    result = gate({"closed_market_paper_trade": True,
                   "protected_demo_bracket_verified": True})
    assert not result["ready_for_live_review"]
    assert "out_of_sample_positive_net_expectancy" in result["missing"]


def test_full_evidence_only_allows_review():
    fields = ("closed_market_paper_trade", "out_of_sample_positive_net_expectancy",
              "protected_demo_bracket_verified", "live_order_adapter_reviewed",
              "kill_switch_and_reconciliation_verified")
    result = gate(dict.fromkeys(fields, True))
    assert result["ready_for_live_review"]
    assert result["live_armed"] is False
