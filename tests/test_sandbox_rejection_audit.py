import os
import sqlite3
import tempfile
import unittest
from futures_engine.sandbox_rejection_audit import record_rejection

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = os.path.join(self.temp.name, "audit.sqlite3")

    def test_same_message_same_reason_is_idempotent(self):
        for _ in range(3):
            record_rejection(db_path=self.path, message_id="m", reason="stale candidate")
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM sandbox_terminal_rejections"
            ).fetchone()[0], 1)

    def test_reason_conflict_is_fail_closed(self):
        record_rejection(db_path=self.path, message_id="m", reason="stale candidate")
        with self.assertRaisesRegex(ValueError, "conflict"):
            record_rejection(db_path=self.path, message_id="m",
                             reason="expired or future signature")

    def test_unknown_reason_is_not_persisted(self):
        with self.assertRaisesRegex(ValueError, "unsupported"):
            record_rejection(db_path=self.path, message_id="m", reason="bad hmac")
        self.assertFalse(os.path.exists(self.path))

    def test_missing_id_rejected(self):
        with self.assertRaisesRegex(ValueError, "message id"):
            record_rejection(db_path=self.path, message_id="", reason="stale candidate")

if __name__ == "__main__":
    unittest.main()
