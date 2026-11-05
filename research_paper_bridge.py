"""Read-only bridge: independently verified Binance research -> indicative paper plans.

No authenticated exchange clients, order placement, or execution permissions.
A plan is NOT a fill. Stale signals are rejected, never replayed as trades.
"""
import json
import sqlite3
import time
from pathlib import Path

from demo_plan_bridge import build_plan
from futures_engine.research_sqs_preview import preview

SOURCE = "/opt/signalpilot/research-history.sqlite3"
JOURNAL = "/opt/signalpilot/demo-plan-journal.sqlite3"


def normalized_signal(record, *, now):
    """Validate original signed-research record, then build verifier input."""
    checked = preview(record, now=now)
    original = record["payload"]
    compact = checked["payload"]
    strategy = original.get("strategy")
    if not isinstance(strategy, str) or not strategy or len(strategy) > 80:
        raise ValueError("invalid_strategy")
    return {
        "signal_id": record["signal_id"],
        "symbol": record["symbol"],
        "direction": compact["direction"],
        "score": compact["score"],
        "strategy": strategy,
        "closed_5m_candle_ms": record["candle_ms"],
        "timestamp": compact["timestamp"],
        "source": compact["source"],
    }


def run(source=SOURCE, journal=JOURNAL, *, now=None, planner=build_plan):
    now = int(time.time()) if now is None else int(now)
    # SQLite source is opened read-only; no edits to scanner or Telegram state.
    source_uri = Path(source).resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(source_uri, uri=True) as db:
        rows = db.execute(
            "SELECT signal_id,symbol,candle_ms,state,payload "
            "FROM research_outbox ORDER BY candle_ms DESC LIMIT 250"
        ).fetchall()
    stats = {"planned": 0, "blocked": 0, "already_seen": 0,
             "orders_sent": False, "mode": "INDICATIVE_ONLY"}
    with sqlite3.connect(journal, timeout=15) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS research_paper_plans (
            signal_id TEXT PRIMARY KEY, symbol TEXT NOT NULL,
            candle_ms INTEGER NOT NULL, status TEXT NOT NULL,
            reason TEXT NOT NULL, plan_json TEXT,
            checked_at INTEGER NOT NULL)""")
        for sid, symbol, candle, state, raw in reversed(rows):
            if db.execute("SELECT 1 FROM research_paper_plans WHERE signal_id=?",
                          (sid,)).fetchone():
                stats["already_seen"] += 1
                continue
            result = None
            try:
                if not isinstance(sid, str) or not sid or len(sid) > 128:
                    raise ValueError("invalid_signal_id")
                if type(candle) is not int or candle % 300000:
                    raise ValueError("invalid_candle")
                payload = json.loads(raw)
                record = {"signal_id": sid, "symbol": symbol,
                          "candle_ms": candle, "state": state, "payload": payload}
                normalized = normalized_signal(record, now=now)
                # build_plan independently recomputes the 5m/4h setup from
                # Binance Futures, checks filters, and caps buffered risk.
                result = planner(normalized, now_ms=now * 1000)
                if not isinstance(result, dict) or result.get("orders_sent") is not False:
                    raise ValueError("unsafe_plan_result")
                if result.get("execution_authorized") is not False:
                    raise ValueError("execution_must_be_disabled")
                if result.get("signal_id") != sid:
                    raise ValueError("plan_signal_mismatch")
                status, reason = "INDICATIVE_PLAN_ONLY", "no_order_submitted"
                stats["planned"] += 1
            except Exception as exc:
                status, reason = "BLOCKED", (type(exc).__name__ + ": " + str(exc))[:180]
                stats["blocked"] += 1
            db.execute(
                "INSERT INTO research_paper_plans VALUES (?,?,?,?,?,?,?)",
                (sid, symbol, candle, status, reason,
                 json.dumps(result, sort_keys=True) if status == "INDICATIVE_PLAN_ONLY" else None,
                 now))
        db.commit()
    return stats


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
