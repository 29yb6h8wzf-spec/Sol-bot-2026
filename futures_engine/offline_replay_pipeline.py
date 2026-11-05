"""Offline replay orchestration: validated plan + supplied historical data -> journal.

No network access, no credentials, no Binance clients, no orders. This is not
an authenticated data feed or a pre-trade risk manager.
"""
from datetime import datetime, timezone
from .offline_history_boundary import replay_verified_history
from .offline_replay_journal import record_result, summary

def process_one(*, plan, history, journal_path):
    if not isinstance(plan, dict):
        raise ValueError("invalid_plan")
    signal_id = plan.get("signal_id")
    if not isinstance(signal_id, str) or not signal_id:
        raise ValueError("missing_signal_id")
    candle_ms = plan.get("closed_5m_candle_ms")
    if type(candle_ms) is not int or candle_ms <= 0:
        raise ValueError("invalid_signal_timestamp")
    # UTC day is derived from signal time, never arbitrary user-supplied day.
    day = datetime.fromtimestamp(candle_ms / 1000, tz=timezone.utc).date().isoformat()
    evaluated = replay_verified_history(plan, history)
    journaled = record_result(
        journal_path, signal_id=signal_id,
        history_sha256=evaluated["history_sha256"],
        replay_record=evaluated["result"], day_utc=day)
    return {"signal_id": signal_id, "day_utc": day,
            "journal": journaled, "summary": summary(journal_path, day_utc=day),
            "history_sha256": evaluated["history_sha256"],
            "provenance": evaluated["source"], "orders_sent": False}
