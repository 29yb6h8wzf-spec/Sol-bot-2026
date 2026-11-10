"""Fail-closed V2 replacement readiness decision. Research-only."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ReplacementEvidence:
    v2_oos_independent_trades: int = 0
    v2_oos_weeks: int = 0
    locked_oos_periods: int = 0
    positive_net_expectancy_each_period: bool = False
    positive_weekly_bootstrap_lower_bound: bool = False
    ab_same_data_same_costs: bool = False
    v2_net_edge_over_old: bool = False
    ab_uncertainty_supports_improvement: bool = False
    independent_verifier_compatible: bool = False
    shadow_mode_passed: bool = False
    rollback_tested: bool = False
    telegram_contract_tested: bool = False
    correlation_and_risk_gates_tested: bool = False


@dataclass(frozen=True)
class ReplacementDecision:
    status: str
    blockers: tuple[str, ...]
    execution_authorized: bool = False


def assess(e: ReplacementEvidence) -> ReplacementDecision:
    if not isinstance(e, ReplacementEvidence):
        raise TypeError("ReplacementEvidence required")
    checks = {
        "insufficient_oos_trades": e.v2_oos_independent_trades >= 200,
        "insufficient_oos_weeks": e.v2_oos_weeks >= 8,
        "missing_locked_oos_periods": e.locked_oos_periods >= 2,
        "nonpositive_oos_expectancy": e.positive_net_expectancy_each_period,
        "uncertain_oos_edge": e.positive_weekly_bootstrap_lower_bound,
        "missing_fair_ab": e.ab_same_data_same_costs,
        "no_demonstrated_net_improvement": e.v2_net_edge_over_old,
        "uncertain_ab_improvement": e.ab_uncertainty_supports_improvement,
        "verifier_incompatible": e.independent_verifier_compatible,
        "shadow_not_validated": e.shadow_mode_passed,
        "rollback_not_tested": e.rollback_tested,
        "telegram_not_tested": e.telegram_contract_tested,
        "risk_gates_not_tested": e.correlation_and_risk_gates_tested,
    }
    blockers = tuple(name for name, passed in checks.items() if not passed)
    # CONDITIONAL is reserved for models with proven OOS+AB edge but pending
    # integration tests. Absence of profitability evidence is NOT_READY.
    scientific = tuple(checks)[:8]
    if any(not checks[k] for k in scientific):
        status = "NOT_READY"
    elif blockers:
        status = "CONDITIONAL"
    else:
        status = "READY_TO_REPLACE"
    return ReplacementDecision(status, blockers)
