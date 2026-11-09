"""Post-cutover gate refuses incomplete or unsafe deployments."""
from futures_engine.research_publish_deploy_gate import (
    DeploymentSnapshot, assess,
)


def snapshot(**changes):
    values = dict(
        old_publisher_active=False,
        new_publisher_active=True,
        legacy_rows_unreconciled=0,
        new_code_ci_passed=True,
        rollback_plan_verified=True,
        paper_only=True,
    )
    values.update(changes)
    return DeploymentSnapshot(**values)


def test_safe_new_only_publisher_snapshot():
    assert assess(snapshot()) == {"ready": True, "blockers": []}


def test_old_only_is_not_cutover_ready():
    result = assess(snapshot(old_publisher_active=True, new_publisher_active=False))
    assert not result["ready"]
    assert "new publisher not active" in result["blockers"]


def test_dual_active_publishers_blocked():
    result = assess(snapshot(old_publisher_active=True))
    assert not result["ready"]
    assert "dual publisher active" in result["blockers"]


def test_unreconciled_legacy_rows_blocked():
    result = assess(snapshot(legacy_rows_unreconciled=1))
    assert "legacy rows require reconciliation" in result["blockers"]


def test_missing_ci_rollback_or_paper_boundary_blocked():
    result = assess(snapshot(
        new_code_ci_passed=False,
        rollback_plan_verified=False,
        paper_only=False,
    ))
    assert len(result["blockers"]) == 3
