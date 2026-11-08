import os
import sqlite3
import tempfile
import unittest
from futures_engine.sandbox_rejection_integration import handle_failed_message

class FakeSQS:
    def __init__(self):
        self.deleted = []
    def delete_message(self, **kw):
        self.deleted.append(kw)

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = os.path.join(self.temp.name, "audit.sqlite3")
        self.sqs = FakeSQS()
        self.msg = {"MessageId": "m-1", "ReceiptHandle": "r-1"}

    def run_rejection(self, exc, **kwargs):
        return handle_failed_message(
            sqs=self.sqs, queue_url="sandbox-only", message=self.msg,
            exc=exc, audit_db=self.db, **kwargs)

    def test_terminal_rejection_persists_before_delete(self):
        self.assertEqual(self.run_rejection(ValueError("stale candidate")), "deleted")
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute(
                "SELECT reason FROM sandbox_terminal_rejections WHERE message_id='m-1'"
            ).fetchone(), ("stale candidate",))
        self.assertEqual(self.sqs.deleted, [
            {"QueueUrl": "sandbox-only", "ReceiptHandle": "r-1"}])

    def test_repeated_rejection_audit_is_idempotent(self):
        for _ in range(2):
            self.run_rejection(ValueError("stale candidate"))
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM sandbox_terminal_rejections"
            ).fetchone()[0], 1)

    def test_unknown_error_is_not_deleted(self):
        self.assertEqual(self.run_rejection(ValueError("bad hmac")), "retry")
        self.assertEqual(self.sqs.deleted, [])
        self.assertFalse(os.path.exists(self.db))

    def test_audit_failure_never_deletes(self):
        bad_path = os.path.join(self.temp.name, "missing", "audit.sqlite3")
        with self.assertRaises(sqlite3.OperationalError):
            handle_failed_message(sqs=self.sqs, queue_url="sandbox-only",
                message=self.msg, exc=ValueError("stale candidate"),
                audit_db=bad_path)
        self.assertEqual(self.sqs.deleted, [])

    def test_conflicting_reason_blocks_deletion(self):
        self.run_rejection(ValueError("stale candidate"))
        self.sqs.deleted.clear()
        with self.assertRaises(ValueError):
            self.run_rejection(ValueError("expired or future signature"))
        self.assertEqual(self.sqs.deleted, [])

if __name__ == "__main__":
    unittest.main()
