"""Offline tests for inbox -> demo router. No exchange connectivity."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from demo_signal_router import connect_inbox, evaluate


def valid(now=1000):
    return {"signal_id": "sig-1", "timestamp": now, "score": 100, "source": "verified_85_score_engine"}


def verifier(p):
    return {"signal_id": p["signal_id"], "symbol": "XRP/USDT:USDT",
            "source": "verified_85_score_engine", "score": 85,
            "side": "long", "entry": 2, "stop": 1.9, "target": 2.2, "quantity": 1}


class RouterTests(unittest.TestCase):
    def test_untrusted_claim_never_authorizes(self):
        self.assertEqual(evaluate(valid(), now=1000)[0], "BLOCKED_UNVERIFIED")

    def test_stale_rejected(self):
        self.assertEqual(evaluate(valid(), now=1121)[0], "REJECTED")

    def test_future_rejected(self):
        self.assertEqual(evaluate(valid(1001), now=1000)[0], "REJECTED")

    def test_independent_score_below_threshold(self):
        def weak(p):
            return {**verifier(p), "score": 84}
        self.assertEqual(evaluate(valid(), verifier=weak, now=1000)[0], "REJECTED")

    def test_risk_preflight_required(self):
        self.assertEqual(evaluate(valid(), verifier=verifier, now=1000)[0], "BLOCKED_PREFLIGHT")

    def test_approved_is_not_an_order(self):
        status, _ = evaluate(valid(), verifier=verifier,
                             preflight=lambda intent, account: (True, "ok"),
                             account={"equity": 150}, now=1000)
        self.assertEqual(status, "DEMO_ELIGIBLE_NOT_SUBMITTED")

    def test_risk_rejection(self):
        status, reason = evaluate(valid(), verifier=verifier,
                                  preflight=lambda intent, account: (False, "risk_limit"),
                                  account={"equity": 150}, now=1000)
        self.assertEqual((status, reason), ("REJECTED_RISK", "risk_limit"))

    def test_inbox_journal_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            inbox, journal = Path(tmp) / "inbox.db", Path(tmp) / "route.db"
            with sqlite3.connect(inbox) as db:
                db.execute("CREATE TABLE signals (signal_id TEXT PRIMARY KEY, received_at INTEGER NOT NULL, payload TEXT NOT NULL)")
                db.execute("INSERT INTO signals VALUES (?,?,?)", ("sig-1", 1000, json.dumps(valid())))
            first = connect_inbox(inbox, journal, now=1000)
            second = connect_inbox(inbox, journal, now=1000)
            self.assertEqual(len(first), 1)
            self.assertEqual(first[0]["status"], "BLOCKED_UNVERIFIED")
            self.assertFalse(first[0]["orders_sent"])
            self.assertEqual(second, [])


if __name__ == "__main__":
    unittest.main()
