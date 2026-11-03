"""Signal inbox -> demo eligibility journal (NO exchange orders).

The incoming payload is untrusted. The caller MUST provide an independent
verifier that recomputes the signal from market data. Without one every
signal is blocked. This module never imports exchange clients or keys.
"""
import json
import sqlite3
import time
from pathlib import Path

ALLOWED = frozenset({"BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT"})


def evaluate(payload, *, verifier=None, preflight=None, account=None, now=None):
    now = int(time.time()) if now is None else int(now)
    if not isinstance(payload, dict):
        return "REJECTED", "invalid_payload"
    sid = payload.get("signal_id")
    if not isinstance(sid, str) or not sid or len(sid) > 128:
        return "REJECTED", "invalid_signal_id"
    ts = payload.get("timestamp")
    if type(ts) is not int or not 0 <= now - ts <= 120:
        return "REJECTED", "stale_or_future_signal"
    if verifier is None:
        return "BLOCKED_UNVERIFIED", "independent_verifier_missing"
    try:
        # Verifier must derive its OWN market data and score, not trust the
        # incoming payload's source/score/price fields.
        verified = verifier(payload)
        if not isinstance(verified, dict) or verified.get("signal_id") != sid:
            return "BLOCKED_UNVERIFIED", "verification_failed"
        if verified.get("symbol") not in ALLOWED:
            return "REJECTED", "unsupported_symbol"
        if verified.get("source") != "verified_85_score_engine":
            return "BLOCKED_UNVERIFIED", "invalid_verified_source"
        if type(verified.get("score")) is not int or verified["score"] < 85 or verified["score"] > 100:
            return "REJECTED", "score_below_85"
        if preflight is None or account is None:
            return "BLOCKED_PREFLIGHT", "risk_preflight_missing"
        allowed, reason = preflight(verified, account)
        if not allowed:
            return "REJECTED_RISK", str(reason)
        return "DEMO_ELIGIBLE_NOT_SUBMITTED", "awaiting_demo_executor"
    except Exception as exc:
        return "BLOCKED_VERIFICATION_ERROR", type(exc).__name__


def connect_inbox(inbox_path, journal_path, *, verifier=None, preflight=None, account=None, now=None):
    """Read existing signal inbox and journal exactly once; no orders placed."""
    inbox_path, journal_path = Path(inbox_path), Path(journal_path)
    if not inbox_path.is_file():
        raise FileNotFoundError("signal inbox missing")
    with sqlite3.connect(str(inbox_path)) as inbox:
        rows = inbox.execute("SELECT signal_id,payload FROM signals ORDER BY received_at").fetchall()
    results = []
    with sqlite3.connect(str(journal_path)) as journal:
        journal.execute("""CREATE TABLE IF NOT EXISTS demo_signal_route (
            signal_id TEXT PRIMARY KEY, status TEXT NOT NULL,
            reason TEXT NOT NULL, checked_at INTEGER NOT NULL)""")
        for sid, raw in rows:
            if not isinstance(sid, str) or not sid or len(sid) > 128:
                continue
            if journal.execute("SELECT 1 FROM demo_signal_route WHERE signal_id=?", (sid,)).fetchone():
                continue
            try:
                payload = json.loads(raw)
            except (TypeError, ValueError):
                payload = None
            if isinstance(payload, dict) and payload.get("signal_id") != sid:
                status, reason = "REJECTED", "signal_id_mismatch"
            else:
                status, reason = evaluate(payload, verifier=verifier, preflight=preflight, account=account, now=now)
            journal.execute("INSERT INTO demo_signal_route VALUES (?,?,?,?)",
                            (sid, status, reason, int(time.time())))
            results.append({"signal_id": sid, "status": status, "reason": reason, "orders_sent": False})
    return results


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--inbox", default="/opt/signalpilot/signal-inbox.sqlite3")
    p.add_argument("--journal", default="/opt/signalpilot/demo-signal-route.sqlite3")
    args = p.parse_args()
    # Recompute signal independently from Binance Futures market data.
    # Risk preflight is intentionally absent: no demo orders are authorized.
    from demo_independent_verifier import verify
    for result in connect_inbox(args.inbox, args.journal, verifier=verify):
        print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
