"""Read-only router economic-event idempotency tests."""
import json
import sqlite3
from demo_signal_router import connect_inbox


def test_two_telegram_ids_one_verified_event(tmp_path):
    inbox, journal = tmp_path / "inbox.sqlite", tmp_path / "journal.sqlite"
    with sqlite3.connect(inbox) as db:
        db.execute("CREATE TABLE signals (signal_id TEXT PRIMARY KEY, received_at INTEGER NOT NULL, payload TEXT NOT NULL)")
        for i, sid in enumerate(("a", "b")):
            db.execute("INSERT INTO signals VALUES (?,?,?)",
                       (sid, i, json.dumps({"signal_id": sid, "timestamp": 1000})))
    def verify(payload):
        return {"signal_id": payload["signal_id"], "source": "verified_85_score_engine",
                "symbol": "BTC/USDT:USDT", "strategy": "EMA_ADX", "direction": "long",
                "closed_5m_candle_ms": 300000, "score": 90,
                "verification": {"independent": True}}
    results = connect_inbox(inbox, journal, verifier=verify,
                            preflight=lambda verified, account: (True, "ok"),
                            account={"equity": 150}, now=1000)
    assert [r["status"] for r in results] == [
        "DEMO_ELIGIBLE_NOT_SUBMITTED", "REJECTED_DUPLICATE"]
    assert connect_inbox(inbox, journal, verifier=verify,
                         preflight=lambda v,a: (True, "ok"),
                         account={"equity": 150}, now=1000) == []
    with sqlite3.connect(journal) as db:
        assert db.execute("SELECT COUNT(*) FROM demo_event_claims").fetchone()[0] == 1


def test_missing_verified_identity_fails_closed(tmp_path):
    inbox, journal = tmp_path / "inbox.sqlite", tmp_path / "journal.sqlite"
    with sqlite3.connect(inbox) as db:
        db.execute("CREATE TABLE signals (signal_id TEXT PRIMARY KEY, received_at INTEGER NOT NULL, payload TEXT NOT NULL)")
        db.execute("INSERT INTO signals VALUES (?,?,?)",
                   ("a", 1, json.dumps({"signal_id": "a", "timestamp": 1000})))
    results = connect_inbox(inbox, journal, verifier=lambda p: {
        "signal_id": p["signal_id"], "symbol": "BTC/USDT:USDT",
        "source": "verified_85_score_engine", "score": 90},
        preflight=lambda v,a: (True, "ok"), account={}, now=1000)
    assert results[0]["status"] == "BLOCKED_UNVERIFIED"
