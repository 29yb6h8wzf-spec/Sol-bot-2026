"""Offline point-in-time order-book sampling audit.

Integrity-only checks: these do not authenticate the source of any sample.
"""
from decimal import Decimal, InvalidOperation


def audit_orderbook_coverage(samples, decision_times, symbol, max_age_ms):
    if type(symbol) is not str or not symbol:
        raise ValueError("invalid_orderbook_symbol")
    if type(max_age_ms) is not int or max_age_ms < 0:
        raise ValueError("invalid_orderbook_max_age")
    if type(decision_times) not in (tuple, list):
        raise ValueError("invalid_orderbook_schedule")
    schedule = tuple(decision_times)
    if not schedule or any(type(t) is not int or t < 0 for t in schedule) or any(
        b <= a for a, b in zip(schedule, schedule[1:])
    ):
        raise ValueError("invalid_orderbook_schedule")
    if type(samples) not in (tuple, list):
        raise ValueError("invalid_orderbook_samples")
    observed = {}
    for sample in samples:
        if type(sample) is not dict or sample.get("symbol") != symbol:
            raise ValueError("invalid_orderbook_sample")
        t = sample.get("timestamp_ms")
        if type(t) is not int or t < 0:
            raise ValueError("invalid_orderbook_sample")
        for field in ("spread_bps", "bid_depth_10bps_usd", "ask_depth_10bps_usd"):
            value = sample.get(field)
            if type(value) is not str:
                raise ValueError("invalid_orderbook_sample")
            try:
                number = Decimal(value)
            except (InvalidOperation, ValueError):
                raise ValueError("invalid_orderbook_sample") from None
            if not number.is_finite() or number < 0:
                raise ValueError("invalid_orderbook_sample")
        if t in observed:
            raise ValueError("duplicate_orderbook_timestamp")
        observed[t] = sample
    times = sorted(observed)
    missing = []
    stale = []
    matched = []
    from bisect import bisect_right
    for decision in schedule:
        idx = bisect_right(times, decision) - 1
        if idx < 0:
            missing.append(decision)
            continue
        age = decision - times[idx]
        if age > max_age_ms:
            stale.append(decision)
        else:
            matched.append((decision, times[idx]))
    return {
        "symbol": symbol,
        "expected_decisions": len(schedule),
        "matched_decision_samples": tuple(matched),
        "missing_decisions": tuple(missing),
        "stale_decisions": tuple(stale),
        "orderbook_coverage_complete": not missing and not stale,
        "orderbook_history_verified": False,
        "provider_authenticity_verified": False,
    }
