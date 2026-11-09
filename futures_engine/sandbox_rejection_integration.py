"""Adapter for EC2 sandbox_research_consumer.poll_once.

Call handle_failed_message in its existing rejection handler. The original
process(), HMAC verification and successful-message delete path stay unchanged.
"""
from functools import partial

from futures_engine.sandbox_rejection_audit import record_rejection
from futures_engine.sandbox_rejection_policy import handle_rejection

DEFAULT_AUDIT_DB = "/opt/signalpilot/sandbox-rejections.sqlite3"

def handle_failed_message(*, sqs, queue_url, message, exc, audit_db=DEFAULT_AUDIT_DB):
    return handle_rejection(
        message=message,
        exc=exc,
        audit=partial(record_rejection, db_path=audit_db),
        delete=lambda *, receipt_handle: sqs.delete_message(
            QueueUrl=queue_url, ReceiptHandle=receipt_handle
        ),
    )
