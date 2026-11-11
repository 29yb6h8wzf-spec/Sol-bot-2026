"""Read-only bridge: independently verified Binance research -> indicative paper plans.

No authenticated exchange clients, order placement, or execution permissions.
A plan is NOT a fill. Stale signals are rejected, never replayed as trades.
"""
import json
from decimal import Decimal, InvalidOperation
import sqlite3
import time
from pathlib import Path

from demo_plan_bridge import build_plan
from futures_engine.market import MarketDataUnavailable
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



def validate_indicative_plan(result, normalized):
    """Fail closed on incomplete, malformed, or mislabeled planner output."""
    if not isinstance(result, dict):
        raise ValueError("unsafe_plan_result")
    if result.get("orders_sent") is not False or result.get("execution_authorized") is not False:
        raise ValueError("execution_must_be_disabled")
    if result.get("risk_snapshot_approved") is not False:
        raise ValueError("risk_snapshot_must_be_unapproved")
    if result.get("status") != "INDICATIVE_PLAN_ONLY_NOT_EXECUTABLE":
        raise ValueError("unexpected_plan_status")
    if result.get("signal_id") != normalized["signal_id"]:
        raise ValueError("plan_signal_mismatch")
    if result.get("symbol") != normalized["symbol"]:
        raise ValueError("plan_symbol_mismatch")
    if result.get("side") != normalized["direction"]:
        raise ValueError("plan_direction_mismatch")
    if result.get("closed_5m_candle_ms") != normalized["closed_5m_candle_ms"]:
        raise ValueError("plan_candle_mismatch")
    try:
        entry, stop, target, qty, risk, notional = (
            Decimal(str(result[key])) for key in
            ("entry", "stop", "target", "quantity",
             "estimated_loss_including_buffer", "estimated_notional")
        )
    except (KeyError, ValueError, TypeError, InvalidOperation) as exc:
        raise ValueError("invalid_plan_numbers") from exc
    if not all(v.is_finite() and v > 0 for v in
               (entry, stop, target, qty, risk, notional)):
        raise ValueError("nonpositive_or_nonfinite_plan")
    if normalized["direction"] == "long" and not stop < entry < target:
        raise ValueError("invalid_long_brackets")
    if normalized["direction"] == "short" and not target < entry < stop:
        raise ValueError("invalid_short_brackets")
    if risk > Decimal("1.50") or notional > Decimal("300"):
        raise ValueError("plan_risk_cap_exceeded")
    if abs(qty * entry - notional) > Decimal("0.000001"):
        raise ValueError("plan_notional_mismatch")
    return result


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
            previous = db.execute(
                "SELECT status FROM research_paper_plans WHERE signal_id=?", (sid,)
            ).fetchone()
            if previous and previous[0] != "RETRY_MARKET_DATA":
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
                validate_indicative_plan(result, normalized)
                status, reason = "INDICATIVE_PLAN_ONLY", "no_order_submitted"
            except MarketDataUnavailable as exc:
                status, reason = "RETRY_MARKET_DATA", str(exc)[:180]
            except Exception as exc:
                status, reason = "BLOCKED", (type(exc).__name__ + ": " + str(exc))[:180]
            saved = db.execute(
                """INSERT INTO research_paper_plans VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(signal_id) DO UPDATE SET status=excluded.status,
                       reason=excluded.reason, plan_json=excluded.plan_json,
                       checked_at=excluded.checked_at
                   WHERE research_paper_plans.status='RETRY_MARKET_DATA'
                     AND excluded.checked_at >= research_paper_plans.checked_at""",
                (sid, symbol, candle, status, reason,
                 json.dumps(result, sort_keys=True) if status == "INDICATIVE_PLAN_ONLY" else None,
                 now))
            if not saved.rowcount:
                stats["already_seen"] += 1
            elif status == "INDICATIVE_PLAN_ONLY":
                stats["planned"] += 1
            else:
                stats["blocked"] += 1
        db.commit()
    return stats


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
