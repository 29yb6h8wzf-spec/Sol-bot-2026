"""SQLite audit trail for read-only research scans; never sends orders."""
import json
import sqlite3
import time

DB = "/opt/signalpilot/research-history.sqlite3"


def record(result, *, db=DB, observed_at=None):
    if not isinstance(result, dict) or result.get("symbol") not in (
        "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT"
    ):
        raise ValueError("invalid research result")
    if result.get("status") not in ("RESEARCH_ONLY", "BLOCKED"):
        raise ValueError("unexpected status")
    if result.get("sqs_sent") is not False or result.get("orders_sent") is not False:
        raise ValueError("non-research result")
    timestamp = int(time.time()) if observed_at is None else int(observed_at)
    candle = result.get("closed_5m_candle_ms")
    if candle is not None and (type(candle) is not int or candle <= 0):
        raise ValueError("invalid candle")
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True)
    with sqlite3.connect(db, timeout=10) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS research_scans ("
                           "id INTEGER PRIMARY KEY, observed_at INTEGER NOT NULL, "
                           "symbol TEXT NOT NULL, candle_ms INTEGER, "
                           "status TEXT NOT NULL, payload TEXT NOT NULL)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_research_time "
                           "ON research_scans(observed_at)")
        connection.execute(
            "INSERT INTO research_scans(observed_at,symbol,candle_ms,status,payload) "
            "VALUES (?,?,?,?,?)",
            (timestamp, result["symbol"], candle, result["status"], payload))
    return True
