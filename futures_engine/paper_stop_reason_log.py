"""Offline-safe per-market, per-closed-candle Paper scan accounting.

No credentials, order submission, or trading decisions. Files are private and
atomically replaced. A file is scoped to a single market by its caller.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

VALID = {"data_rejected", "no_cross", "rsi_fail", "signal"}
SUBREASONS = {"stale", "gap", "insufficient", "other"}


def data_subreason(exc):
    message = str(exc).lower()
    if "stale" in message:
        return "stale"
    if "gap" in message or "invalid_binance_market_data" in message:
        return "gap"
    if "insufficient" in message:
        return "insufficient"
    return "other"


def reason_for(signal, diagnosis):
    if signal in ("long", "short"):
        return "signal"
    condition = diagnosis["condition"]
    if condition == "NO_EMA_CROSS":
        return "no_cross"
    if condition in ("LONG_CROSS_RSI_NOT_BELOW_55", "SHORT_CROSS_RSI_NOT_ABOVE_45"):
        return "rsi_fail"
    raise ValueError("unrecognized_signal_filter_condition")


def record(path, market, candle_ms, reason, subreason=None):
    """Record once per closed candle; return False for an already counted candle.

    data_rejected has no trustworthy closed-candle timestamp: each failed scan
    is counted, never confused with a successfully validated candle.
    """
    if reason not in VALID:
        raise ValueError("invalid_stop_reason")
    if reason == "data_rejected":
        if subreason not in SUBREASONS:
            raise ValueError("invalid_data_rejection_reason")
    elif subreason is not None:
        raise ValueError("unexpected_subreason")
    if not isinstance(market, str) or not market or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" for c in market):
        raise ValueError("invalid_market")
    if candle_ms is not None and (not isinstance(candle_ms, int) or candle_ms < 0):
        raise ValueError("invalid_candle_timestamp")
    if reason != "data_rejected" and candle_ms is None:
        raise ValueError("missing_closed_candle")
    day = datetime.fromtimestamp(candle_ms / 1000, timezone.utc).strftime("%Y-%m-%d") if candle_ms is not None else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    state = json.loads(path.read_text()) if path.exists() else {"market": market, "days": {}, "last_closed_candle": None}
    if state["market"] != market:
        raise ValueError("audit_market_mismatch")
    if candle_ms is not None and state["last_closed_candle"] is not None and candle_ms <= state["last_closed_candle"]:
        return False
    day_data = state["days"].setdefault(day, {"data_rejected": 0, "no_cross": 0, "rsi_fail": 0, "signal": 0, "data_subreasons": {k: 0 for k in sorted(SUBREASONS)}})
    day_data[reason] += 1
    if subreason is not None:
        day_data["data_subreasons"][subreason] += 1
    if candle_ms is not None:
        state["last_closed_candle"] = candle_ms
    temp = path.with_name(path.name + ".tmp." + str(os.getpid()))
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(state, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()
    return True
