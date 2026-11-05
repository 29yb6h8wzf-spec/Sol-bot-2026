"""Durable idempotent research outbox. Never publishes to SQS or places orders."""
import json
import sqlite3

DB = "/opt/signalpilot/research-history.sqlite3"

def stage(result, *, db=DB):
    if result.get("status") != "RESEARCH_ONLY":
        return 0
    staged = 0
    with sqlite3.connect(db, timeout=15) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS research_outbox ("
            "signal_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, "
            "candle_ms INTEGER NOT NULL, payload TEXT NOT NULL, "
            "state TEXT NOT NULL DEFAULT 'PENDING_REVIEW' "
            "CHECK(state = 'PENDING_REVIEW'))")
        for item in result.get("candidates_85_plus", []):
            verification = item.get("verification", {})
            if (verification.get("status") != "RECALCULATED_RESEARCH_CANDIDATE"
                or verification.get("score_verified_independently") is not True
                or verification.get("execution_authorized") is not False
                or verification.get("sqs_sent") is not False
                or verification.get("orders_sent") is not False
                or verification.get("symbol") != result.get("symbol")
                or verification.get("candle_ms") != result.get("closed_5m_candle_ms")
                or verification.get("score") != item.get("score")
                or verification.get("strategy") != item.get("strategy")
                or verification.get("direction") != item.get("direction")
                or not verification.get("signal_id", "").startswith("research-")):
                raise ValueError("unverified research candidate")
            cursor = conn.execute(
                "INSERT OR IGNORE INTO research_outbox "
                "(signal_id,symbol,candle_ms,payload) VALUES (?,?,?,?)",
                (verification["signal_id"], result["symbol"],
                 verification["candle_ms"], json.dumps(verification, sort_keys=True)))
            staged += cursor.rowcount
    return staged
