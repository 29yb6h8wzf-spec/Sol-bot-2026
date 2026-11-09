"""Read-only post-cutover gate for research publisher migration.

A healthy old publisher is NOT evidence that the new publisher is deployed.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class DeploymentSnapshot:
    old_publisher_active: bool
    new_publisher_active: bool
    legacy_rows_unreconciled: int
    new_code_ci_passed: bool
    rollback_plan_verified: bool
    paper_only: bool


def assess(snapshot):
    blockers = []
    if snapshot.old_publisher_active and snapshot.new_publisher_active:
        blockers.append("dual publisher active")
    if snapshot.old_publisher_active:
        blockers.append("old publisher still active")
    if not snapshot.new_publisher_active:
        blockers.append("new publisher not active")
    if snapshot.legacy_rows_unreconciled:
        blockers.append("legacy rows require reconciliation")
    if not snapshot.new_code_ci_passed:
        blockers.append("new code CI not verified")
    if not snapshot.rollback_plan_verified:
        blockers.append("rollback plan not verified")
    if not snapshot.paper_only:
        blockers.append("paper-only boundary not verified")
    return {"ready": not blockers, "blockers": blockers}
