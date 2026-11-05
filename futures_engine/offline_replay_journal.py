"""Append-only, offline hypothetical result journal.

No Binance API, no order placement. This records independently supplied
replay results, NOT exchange-confirmed trades. Uses SQLite transactional
uniqueness and explicit source fingerprints.
"""
import json
import sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation

DAILY_CAP = Decimal("7.50")

def amount(value):
    try:
        x = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise ValueError("invalid_pnl") from exc
    if not x.is_finite():
        raise ValueError("nonfinite_pnl")
    return x

def record_result(path, *, signal_id, history_sha256, replay_record, day_utc):
    if not isinstance(signal_id, str) or not (1 <= len(signal_id) <= 128):
        raise ValueError("invalid_signal_id")
    if not isinstance(history_sha256, str) or len(history_sha256) != 64 or any(
        c not in "0123456789abcdef" for c in history_sha256):
        raise ValueError("invalid_history_digest")
    if not isinstance(day_utc, str) or len(day_utc) != 10:
        raise ValueError("invalid_day")
    try:
        if date.fromisoformat(day_utc).isoformat() != day_utc:
            raise ValueError("invalid_day")
    except ValueError as exc:
        raise ValueError("invalid_day") from exc
    if not isinstance(replay_record, dict) or replay_record.get("orders_sent") is not False:
        raise ValueError("unsafe_result")
    status = replay_record.get("status")
    if status not in ("CLOSED_HYPOTHETICAL", "OPEN_HYPOTHETICAL", "REJECTED", "UNKNOWN"):
        raise ValueError("invalid_result_status")
    pnl = None
    if status == "CLOSED_HYPOTHETICAL":
        if replay_record.get("exit_reason") not in ("STOP", "TARGET"):
            raise ValueError("invalid_exit_reason")
        pnl = amount(replay_record["net_pnl_excluding_funding"])
    elif "net_pnl_excluding_funding" in replay_record:
        raise ValueError("unclosed_pnl")
    # SQLite path is explicitly supplied by caller; never read production journal.
    with sqlite3.connect(path, timeout=15) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS paper_replay_events (
            signal_id TEXT PRIMARY KEY, history_sha256 TEXT NOT NULL,
            day_utc TEXT NOT NULL, status TEXT NOT NULL,
            pnl_excluding_funding TEXT, result_json TEXT NOT NULL)""")
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            "SELECT history_sha256, result_json, day_utc FROM paper_replay_events WHERE signal_id=?",
            (signal_id,)).fetchone()
        payload = json.dumps(replay_record, sort_keys=True, separators=(",", ":"))
        if existing:
            if existing != (history_sha256, payload, day_utc):
                raise ValueError("conflicting_replay_for_signal")
            return {"inserted": False, "reason": "already_recorded"}
        # Do not confuse this after-the-fact journal with a pre-trade risk
        # reservation system. It flags daily loss but cannot authorize entry.
        db.execute("INSERT INTO paper_replay_events VALUES (?,?,?,?,?,?)",
                   (signal_id, history_sha256, day_utc, status,
                    str(pnl) if pnl is not None else None, payload))
        db.commit()
    return {"inserted": True, "status": status}

def summary(path, *, day_utc):
    with sqlite3.connect(path) as db:
        rows = db.execute(
            "SELECT status, pnl_excluding_funding FROM paper_replay_events WHERE day_utc=?",
            (day_utc,)).fetchall()
    realized = sum((amount(p) for status,p in rows if status == "CLOSED_HYPOTHETICAL"),
                   Decimal("0"))
    return {"day_utc": day_utc, "events": len(rows),
            "closed_hypothetical": sum(s == "CLOSED_HYPOTHETICAL" for s,_ in rows),
            "open_hypothetical": sum(s == "OPEN_HYPOTHETICAL" for s,_ in rows),
            "unknown": sum(s == "UNKNOWN" for s,_ in rows),
            "rejected": sum(s == "REJECTED" for s,_ in rows),
            "realized_hypothetical_pnl_excluding_funding": str(realized),
            "daily_loss_cap_breached": realized <= -DAILY_CAP,
            "risk_authorization": False, "orders_sent": False}
