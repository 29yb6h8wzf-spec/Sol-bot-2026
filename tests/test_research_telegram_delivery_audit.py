"""Offline tests for read-only delivery reconciliation."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from futures_engine.research_telegram_delivery_audit import audit


class DeliveryAuditTests(unittest.TestCase):
    def test_reconcile_without_writing_or_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.sqlite3"
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE research_outbox (signal_id TEXT PRIMARY KEY)")
                db.execute("CREATE TABLE binance_telegram_delivery (signal_id TEXT PRIMARY KEY, status TEXT)")
                db.execute("CREATE TABLE sandbox_publish_log (signal_id TEXT PRIMARY KEY)")
                db.executemany("INSERT INTO research_outbox VALUES (?)", [("a",), ("b",), ("c",)])
                db.executemany("INSERT INTO binance_telegram_delivery VALUES (?,?)",
                               [("a", "DELIVERED_OWNER_ONLY"), ("b", "UNCONFIRMED")])
                db.execute("INSERT INTO sandbox_publish_log VALUES ('c')")
            before = path.read_bytes()
            result = audit(path)
            self.assertEqual(result["total_outbox"], 3)
            self.assertEqual(result["counts"]["delivered_recorded"], 1)
            self.assertEqual(result["counts"]["unconfirmed"], 1)
            self.assertEqual(result["counts"]["missing_delivery_receipt"], 1)
            self.assertEqual(result["counts"]["sandbox_publish_logged"], 1)
            self.assertFalse(result["execution_authorized"])
            self.assertFalse(result["delivery_confirmed_by_telegram"])
            self.assertEqual(path.read_bytes(), before)

    def test_unknown_delivery_status_is_not_counted_as_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.sqlite3"
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE research_outbox (signal_id TEXT PRIMARY KEY)")
                db.execute("CREATE TABLE binance_telegram_delivery (signal_id TEXT PRIMARY KEY, status TEXT)")
                db.execute("CREATE TABLE sandbox_publish_log (signal_id TEXT PRIMARY KEY)")
                db.execute("INSERT INTO research_outbox VALUES ('unknown')")
                db.execute("INSERT INTO binance_telegram_delivery VALUES ('unknown','FAILED')")
            result = audit(path)
            self.assertEqual(result["counts"]["other_status"], 1)
            self.assertEqual(result["counts"]["delivered_recorded"], 0)
            self.assertFalse(result["delivery_confirmed_by_telegram"])

    def test_multiple_sandbox_logs_do_not_duplicate_outbox_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.sqlite3"
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE research_outbox (signal_id TEXT PRIMARY KEY)")
                db.execute("CREATE TABLE binance_telegram_delivery (signal_id TEXT PRIMARY KEY, status TEXT)")
                db.execute("CREATE TABLE sandbox_publish_log (signal_id TEXT)")
                db.execute("INSERT INTO research_outbox VALUES ('one')")
                db.executemany("INSERT INTO sandbox_publish_log VALUES (?)",
                               [('one',), ('one',)])
            report = audit(path)
            self.assertEqual(report["total_outbox"], 1)
            self.assertEqual(report["counts"]["missing_delivery_receipt"], 1)
            self.assertEqual(report["counts"]["sandbox_publish_logged"], 1)

    def test_missing_db_never_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.sqlite3"
            with self.assertRaises(FileNotFoundError):
                audit(path)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
