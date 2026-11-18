"""Offline regression tests for Telegram receipt snapshot comparison."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from futures_engine.research_telegram_delivery_delta import compare, snapshot


class DeliveryDeltaTests(unittest.TestCase):
    def test_new_and_existing_state_changes_are_separate(self):
        baseline = {"old": "missing_delivery_receipt", "good": "delivered_recorded",
                    "gone": "unconfirmed", "stable": "unconfirmed"}
        current = {"old": "delivered_recorded", "good": "unconfirmed",
                   "stable": "unconfirmed", "newbad": "missing_delivery_receipt",
                   "newgood": "delivered_recorded"}
        result = compare(baseline, current)
        self.assertEqual(result["new_signals"], 2)
        self.assertEqual(result["new_unresolved"], 1)
        self.assertEqual(result["resolved_existing"], 1)
        self.assertEqual(result["existing_became_unresolved"], 1)
        self.assertEqual(result["missing_from_current"], 1)
        self.assertFalse(result["execution_authorized"])

    def test_invalid_categories_fail_closed(self):
        with self.assertRaises(ValueError):
            compare({"a": "SUCCESS"}, {"a": "delivered_recorded"})

    def test_snapshot_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "signals.sqlite3"
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE research_outbox (signal_id TEXT PRIMARY KEY)")
                db.execute("CREATE TABLE binance_telegram_delivery (signal_id TEXT PRIMARY KEY, status TEXT)")
                db.executemany("INSERT INTO research_outbox VALUES (?)", [("one",), ("two",)])
                db.execute("INSERT INTO binance_telegram_delivery VALUES ('one','UNCONFIRMED')")
            before = path.read_bytes()
            self.assertEqual(snapshot(path), {"one": "unconfirmed", "two": "missing_delivery_receipt"})
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
