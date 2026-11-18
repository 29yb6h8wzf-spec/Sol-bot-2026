"""Offline funding-event coverage audit; no network or trading access.

This checks timestamp coverage and record integrity, NOT provider authenticity.
"""
from collections import Counter


def audit_funding_coverage(records, expected_event_times, symbol):
    """Return deterministic integrity-only coverage counters.

    Both inputs must be materialized lists/tuples. Exact event timestamps are
    supplied by a separately reviewed exchange-specific funding calendar.
    """
    if type(symbol) is not str or not symbol:
        raise ValueError("invalid_funding_symbol")
    if type(expected_event_times) not in (list, tuple):
        raise ValueError("invalid_funding_schedule")
    schedule = tuple(expected_event_times)
    if (not schedule or any(type(t) is not int or t < 0 for t in schedule)
            or any(b <= a for a, b in zip(schedule, schedule[1:]))):
        raise ValueError("invalid_funding_schedule")
    if type(records) not in (list, tuple):
        raise ValueError("invalid_funding_records")
    observed = []
    for item in records:
        if type(item) is not dict or item.get("symbol") != symbol:
            raise ValueError("invalid_funding_record")
        t = item.get("funding_time_ms")
        rate = item.get("funding_rate")
        if type(t) is not int or t < 0 or type(rate) is not str:
            raise ValueError("invalid_funding_record")
        # Decimal rejects non-finite values and invalid strings; never parse
        # rates as floats for monetary accounting.
        from decimal import Decimal, InvalidOperation
        try:
            parsed = Decimal(rate)
        except (InvalidOperation, ValueError):
            raise ValueError("invalid_funding_record") from None
        if not parsed.is_finite():
            raise ValueError("invalid_funding_record")
        observed.append(t)
    counts = Counter(observed)
    expected = set(schedule)
    missing = tuple(t for t in schedule if counts[t] == 0)
    duplicates = tuple(sorted(t for t, count in counts.items() if count > 1))
    unexpected = tuple(sorted(t for t in counts if t not in expected))
    return {
        "symbol": symbol,
        "expected_events": len(schedule),
        "observed_records": len(records),
        "missing_event_times": missing,
        "duplicate_event_times": duplicates,
        "unexpected_event_times": unexpected,
        "funding_coverage_complete": not (missing or duplicates or unexpected),
        "funding_history_verified": False,
        "provider_authenticity_verified": False,
    }
