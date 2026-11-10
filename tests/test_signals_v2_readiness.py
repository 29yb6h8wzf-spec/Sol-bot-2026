"""Replacement readiness must fail closed without evidence."""
from dataclasses import replace
from signals_v2.readiness import ReplacementEvidence, assess


def test_default_is_not_ready():
    result = assess(ReplacementEvidence())
    assert result.status == "NOT_READY"
    assert result.execution_authorized is False
    assert "missing_fair_ab" in result.blockers


def test_positive_oos_but_no_integration_is_conditional():
    e = ReplacementEvidence(
        v2_oos_independent_trades=200, v2_oos_weeks=8, locked_oos_periods=2,
        positive_net_expectancy_each_period=True,
        positive_weekly_bootstrap_lower_bound=True,
        ab_same_data_same_costs=True, v2_net_edge_over_old=True,
        ab_uncertainty_supports_improvement=True)
    assert assess(e).status == "CONDITIONAL"
    ready = replace(e, independent_verifier_compatible=True,
                    shadow_mode_passed=True, rollback_tested=True,
                    telegram_contract_tested=True,
                    correlation_and_risk_gates_tested=True)
    result = assess(ready)
    assert result.status == "READY_TO_REPLACE"
    assert result.execution_authorized is False
    assert not result.blockers


def test_missing_single_scientific_gate_blocks():
    e = ReplacementEvidence(
        v2_oos_independent_trades=200, v2_oos_weeks=8, locked_oos_periods=2,
        positive_net_expectancy_each_period=True,
        positive_weekly_bootstrap_lower_bound=True,
        ab_same_data_same_costs=True, v2_net_edge_over_old=True,
        ab_uncertainty_supports_improvement=True,
        independent_verifier_compatible=True,
        shadow_mode_passed=True, rollback_tested=True,
        telegram_contract_tested=True,
        correlation_and_risk_gates_tested=True)
    assert assess(replace(e, ab_same_data_same_costs=False)).status == "NOT_READY"
