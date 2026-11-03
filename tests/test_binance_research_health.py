"""Offline tests for Binance research telemetry; never use market APIs."""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from binance_research_health import summarize, save

NOW = 1793725000
SYMBOL = "SOL/USDT:USDT"


class ResearchHealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.research = self.root / "research.sqlite3"
        self.sandbox = self.root / "sandbox.sqlite3"
        with sqlite3.connect(self.research) as db:
            db.execute("CREATE TABLE research_scans (observed_at INTEGER, symbol TEXT, status TEXT, payload TEXT)")
            db.execute("CREATE TABLE research_outbox (signal_id TEXT, candle_ms INTEGER)")
            db.execute("CREATE TABLE sandbox_publish_log (signal_id TEXT, message_id TEXT)")
        with sqlite3.connect(self.sandbox) as db:
            db.execute("CREATE TABLE sandbox_received (research_signal_id TEXT)")
        self.insert()

    def insert(self, *, observed=NOW-30, status="RESEARCH_ONLY",
               score=85, symbol=SYMBOL, rejected=None):
        payload = {"symbol": symbol, "status": status,
                   "candidates_85_plus": [{"score": score}] if score is not None else [],
                   "rejected_candidates": rejected or []}
        with sqlite3.connect(self.research) as db:
            db.execute("INSERT INTO research_scans VALUES (?,?,?,?)",
                       (observed, symbol, status, json.dumps(payload)))

    def report(self, now=NOW):
        return summarize(research_db=self.research, sandbox_db=self.sandbox, now=now)

    def test_85_candidate_count(self):
        r = self.report()
        self.assertEqual(r["counts"]["candidates_85_plus"], 1)
        self.assertEqual(r["status"], "SCANNING")
        self.assertEqual(r["telegram_delivery"], "NOT_CONNECTED_FROM_AWS_RESEARCH")
        self.assertFalse(r["execution_authorized"])

    def test_missing_candidate(self):
        with sqlite3.connect(self.research) as db:
            db.execute("DELETE FROM research_scans")
        self.insert(score=None)
        self.assertEqual(self.report()["counts"]["candidates_85_plus"], 0)

    def test_old_scan_stale(self):
        self.assertEqual(self.report(NOW+1000)["status"], "SCANNER_STALE")

    def test_old_scan_excluded(self):
        self.insert(observed=NOW-90000)
        self.assertEqual(self.report()["counts"]["scan_rows"], 1)

    def test_blocked_scan_count(self):
        self.insert(status="BLOCKED", score=None)
        r = self.report()
        self.assertEqual(r["counts"]["scan_errors"], 1)
        self.assertEqual(r["status"], "RESEARCH_ERRORS")

    def test_rejected_verification_count(self):
        self.insert(score=None, rejected=[{"reason": "failed"}])
        self.assertEqual(self.report()["counts"]["verification_rejected"], 1)

    def test_reject_low_score(self):
        self.insert(score=84)
        with self.assertRaisesRegex(ValueError, "invalid_research_score"):
            self.report()

    def test_reject_boolean_score(self):
        self.insert(score=True)
        with self.assertRaisesRegex(ValueError, "invalid_research_score"):
            self.report()

    def test_reject_unknown_symbol(self):
        self.insert(symbol="DOGE/USDT:USDT")
        with self.assertRaisesRegex(ValueError, "unknown_research_symbol"):
            self.report()

    def test_reject_mismatched_payload(self):
        with sqlite3.connect(self.research) as db:
            db.execute("INSERT INTO research_scans VALUES (?,?,?,?)",
                       (NOW, SYMBOL, "RESEARCH_ONLY",
                        json.dumps({"symbol": "BTC/USDT:USDT", "status": "RESEARCH_ONLY"})))
        with self.assertRaisesRegex(ValueError, "invalid_research_record"):
            self.report()

    def test_missing_db_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "research_database_missing"):
            summarize(research_db=self.root/"missing", sandbox_db=self.sandbox, now=NOW)

    def test_sandbox_distinct_from_telegram(self):
        with sqlite3.connect(self.research) as db:
            db.execute("INSERT INTO sandbox_publish_log VALUES (?,?)", ("a", "msg1"))
            db.execute("INSERT INTO sandbox_publish_log VALUES (?,?)", ("b", "UNCONFIRMED"))
        with sqlite3.connect(self.sandbox) as db:
            db.execute("INSERT INTO sandbox_received VALUES (?)", ("a",))
        r = self.report()
        self.assertEqual(r["counts"]["sandbox_published_total"], 1)
        self.assertEqual(r["counts"]["sandbox_unconfirmed_total"], 1)
        self.assertEqual(r["counts"]["sandbox_received_total"], 1)
        self.assertTrue(r["sandbox_queue_is_not_telegram"])

    def test_outbox_count(self):
        with sqlite3.connect(self.research) as db:
            db.execute("INSERT INTO research_outbox VALUES (?,?)", ("a", (NOW-20)*1000))
        self.assertEqual(self.report()["counts"]["outbox_24h"], 1)

    def test_root_only_file_mode(self):
        path = self.root / "report.json"
        save(self.report(), path=path)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertFalse(json.loads(path.read_text())["orders_sent"])

    def test_no_network_dependency(self):
        self.assertEqual(self.report()["mode"], "RESEARCH_ONLY")


if __name__ == "__main__":
    unittest.main()
