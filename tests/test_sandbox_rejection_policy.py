import unittest
from futures_engine.sandbox_rejection_policy import classify, handle_rejection


class RejectionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.message = {"MessageId": "m-1", "ReceiptHandle": "receipt"}
        self.events = []

    def audit(self, **kw):
        self.events.append(("audit", kw))

    def delete(self, **kw):
        self.events.append(("delete", kw))

    def test_expired_signature_audited_before_delete(self):
        result = handle_rejection(message=self.message,
            exc=ValueError("expired or future signature"),
            audit=self.audit, delete=self.delete)
        self.assertEqual(result, "deleted")
        self.assertEqual([event[0] for event in self.events], ["audit", "delete"])

    def test_stale_candidate_audited_before_delete(self):
        self.assertEqual(handle_rejection(message=self.message,
            exc=ValueError("stale candidate"), audit=self.audit,
            delete=self.delete), "deleted")

    def test_unknown_value_error_never_deleted(self):
        self.assertEqual(handle_rejection(message=self.message,
            exc=ValueError("invalid signature"), audit=self.audit,
            delete=self.delete), "retry")
        self.assertEqual(self.events, [])

    def test_temporary_database_error_retried(self):
        self.assertEqual(handle_rejection(message=self.message,
            exc=RuntimeError("database locked"), audit=self.audit,
            delete=self.delete), "retry")
        self.assertEqual(self.events, [])

    def test_failed_audit_prevents_delete(self):
        def fail_audit(**kw):
            raise OSError("disk full")
        with self.assertRaises(OSError):
            handle_rejection(message=self.message,
                exc=ValueError("stale candidate"), audit=fail_audit,
                delete=self.delete)
        self.assertEqual(self.events, [])

    def test_missing_receipt_never_deleted(self):
        self.assertEqual(handle_rejection(message={"MessageId": "m-1"},
            exc=ValueError("stale candidate"), audit=self.audit,
            delete=self.delete), "retry")
        self.assertEqual(self.events, [])

    def test_delete_failure_propagates_for_retry(self):
        def fail_delete(**kw):
            raise RuntimeError("SQS unavailable")
        with self.assertRaises(RuntimeError):
            handle_rejection(message=self.message,
                exc=ValueError("stale candidate"), audit=self.audit,
                delete=fail_delete)
        self.assertEqual([event[0] for event in self.events], ["audit"])


if __name__ == "__main__":
    unittest.main()
