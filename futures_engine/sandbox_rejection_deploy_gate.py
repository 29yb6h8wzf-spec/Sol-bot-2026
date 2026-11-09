"""Read-only preflight checks for the sandbox rejection patch.

No AWS calls, systemctl mutations, queue receives, deletes or orders.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class Gate:
    ready: bool
    blockers: tuple

def assess(*, ci_passed, consumer_source_reviewed, sandbox_queue_verified,
           durable_audit_tested, mock_sqs_tested, rollback_backup_verified,
           paper_only, dlq_replay_disabled):
    conditions = {
        "CI not green": ci_passed,
        "EC2 consumer source not reviewed": consumer_source_reviewed,
        "sandbox queue not verified": sandbox_queue_verified,
        "durable audit not tested": durable_audit_tested,
        "mock SQS test missing": mock_sqs_tested,
        "rollback backup missing": rollback_backup_verified,
        "paper-only isolation missing": paper_only,
        "DLQ replay not disabled": dlq_replay_disabled,
    }
    blockers = tuple(name for name, passed in conditions.items() if not passed)
    return Gate(ready=not blockers, blockers=blockers)
