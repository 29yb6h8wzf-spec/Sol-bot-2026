"""Fail-closed sandbox SQS rejection policy; no AWS calls or order execution.

A permanent rejection is acknowledged ONLY after an injected durable audit
callback succeeds. An audit failure keeps the message available for retry.
Existing DLQ messages are never replayed by this module.
"""
import json
from dataclasses import dataclass

PERMANENT_REASONS = frozenset({
    "expired or future signature",
    "stale candidate",
})

@dataclass(frozen=True)
class Decision:
    action: str
    reason: str

def classify(exc):
    """Unknown errors are retryable; never broadly delete ValueError messages."""
    reason = str(exc)
    if isinstance(exc, ValueError) and reason in PERMANENT_REASONS:
        return Decision("audit_then_delete", reason)
    return Decision("retry", type(exc).__name__)

def handle_rejection(*, message, exc, audit, delete):
    """Audit must be durable/idempotent and raise if persistence is uncertain.

    Neither body nor receipt handle is written to audit. The caller must supply
    a durable audit store and delete callback bound to the original queue.
    """
    decision = classify(exc)
    if decision.action != "audit_then_delete":
        return "retry"
    message_id = message.get("MessageId")
    receipt = message.get("ReceiptHandle")
    if not isinstance(message_id, str) or not message_id:
        return "retry"
    if not isinstance(receipt, str) or not receipt:
        return "retry"
    audit(message_id=message_id, reason=decision.reason)
    delete(receipt_handle=receipt)
    return "deleted"
