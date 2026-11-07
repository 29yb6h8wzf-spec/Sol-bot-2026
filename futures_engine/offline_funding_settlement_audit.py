"""Pure offline, fail-closed Binance USDT-M funding-settlement research audit.

No network calls, credentials, exchange clients, orders or live account access.
Funding schedules may change by contract and over time: never synthesize a
fixed 8-hour schedule. The caller must supply an independently captured,
complete expected schedule for each symbol. Matching self-declared records
does NOT authenticate Binance as the source.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json

from .offline_90day_coverage_gate import COINS, DAYS, _at_utc_midnight

DAY_MS = 86_400_000
MAX_EVENTS_PER_SYMBOL = 20_000


def _d(value, *, positive=False, rate=False):
    if isinstance(value, bool):
        raise ValueError("invalid_funding_number")
    try:
        v = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("invalid_funding_number") from exc
    if not v.is_finite() or (positive and v <= 0) or (
            rate and abs(v) > Decimal("1")):
        raise ValueError("invalid_funding_number")
    return v


def _time(value):
    return type(value) is int and value >= 0


def _validate_rows(rows, start_ms, end_ms):
    """Canonicalize schedule-linked funding events; no implied missing fills."""
    if not isinstance(rows, (list, tuple)) or len(rows) > MAX_EVENTS_PER_SYMBOL:
        raise ValueError("invalid_funding_rows")
    parsed = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
                "timestamp_ms", "funding_rate", "mark_price"}:
            raise ValueError("invalid_funding_row")
        t = row["timestamp_ms"]
        if not _time(t) or not start_ms <= t < end_ms:
            raise ValueError("invalid_funding_timestamp")
        rate = _d(row["funding_rate"], rate=True)
        mark = _d(row["mark_price"], positive=True)
        parsed.append((t, rate, mark))
    if any(parsed[i][0] >= parsed[i + 1][0]
           for i in range(len(parsed) - 1)):
        raise ValueError("unsorted_or_duplicate_funding")
    return parsed


def _fingerprint(parsed):
    h = sha256()
    for t, rate, mark in parsed:
        h.update(json.dumps([t, str(rate.normalize()), str(mark.normalize())],
                            separators=(",", ":")).encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def audit_funding_90_days(*, start_day, rows_by_symbol,
                          expected_settlements_by_symbol,
                          provenance_by_symbol, observed_as_of_ms):
    """Audit 90 complete UTC days against an EXPLICIT expected schedule.

    A declared exchange name, comparison to a caller-supplied schedule and a
    SHA256 protect internal consistency/reproducibility only. Without a
    separately authenticated publisher or signed archive, the result is
    never called reconciled or usable to authorize production trading.
    """
    start_ms = _at_utc_midnight(start_day)
    end_ms = start_ms + DAYS * DAY_MS
    if not _time(observed_as_of_ms) or observed_as_of_ms < end_ms:
        raise ValueError("incomplete_funding_audit_window")
    for data in (rows_by_symbol, expected_settlements_by_symbol,
                 provenance_by_symbol):
        if not isinstance(data, dict) or set(data) != set(COINS):
            raise ValueError("four_explicit_funding_symbols_required")
    results = {}
    for coin in COINS:
        source = provenance_by_symbol[coin]
        # Keyed funding observations are not sufficient identity evidence:
        # reject a provenance bundle copied from a different instrument.
        # This is still self-declared, NOT independent source authentication.
        if not isinstance(source, dict) or (
                source.get("symbol") != coin or
                source.get("exchange") != "BINANCE" or
                source.get("market") != "USDT_M_FUTURES" or
                source.get("dataset") != "FUNDING_SETTLEMENTS"):
            results[coin] = {"status": "UNVERIFIED_FUNDING_SOURCE"}
            continue
        fetched = source.get("fetched_at_ms")
        through = source.get("complete_through_ms")
        if (not _time(fetched) or not _time(through) or
                not end_ms <= through <= fetched <= observed_as_of_ms):
            results[coin] = {"status": "UNVERIFIED_FUNDING_SOURCE",
                             "reason": "incomplete_or_future_source_window"}
            continue
        schedule = expected_settlements_by_symbol[coin]
        if (not isinstance(schedule, (list, tuple)) or
                not 1 <= len(schedule) <= MAX_EVENTS_PER_SYMBOL):
            results[coin] = {"status": "UNKNOWN_FUNDING_SCHEDULE"}
            continue
        if (any(not _time(t) or not start_ms <= t < end_ms for t in schedule)
                or any(a >= b for a, b in zip(schedule, schedule[1:]))):
            results[coin] = {"status": "INVALID_FUNDING_SCHEDULE"}
            continue
        try:
            parsed = _validate_rows(rows_by_symbol[coin], start_ms, end_ms)
        except ValueError as exc:
            results[coin] = {"status": "INVALID_FUNDING_DATA",
                             "reason": str(exc)}
            continue
        event_times = [r[0] for r in parsed]
        if event_times != list(schedule):
            results[coin] = {
                "status": "INCOMPLETE_FUNDING_SETTLEMENTS",
                "expected_events": len(schedule),
                "observed_events": len(parsed),
                "reason": "missing_extra_or_misaligned_settlement",
            }
            continue
        results[coin] = {
            "status": "COMPLETE_UNAUTHENTICATED",
            "expected_events": len(schedule),
            "observed_events": len(parsed),
            "funding_sha256": _fingerprint(parsed),
        }
    ok = all(v.get("status") == "COMPLETE_UNAUTHENTICATED"
             for v in results.values())
    return {
        "status": ("FUNDING_CONTINUITY_COMPLETE_UNAUTHENTICATED" if ok
                   else "NOT_ENOUGH_VERIFIED_FUNDING"),
        "start_day": start_day,
        "window_start_ms": start_ms,
        "window_end_exclusive_ms": end_ms,
        "symbols": results,
        "schedule_is_caller_supplied_not_authenticated": True,
        "funding_reconciled": False,
        "source_independently_authenticated": False,
        "net_backtest_pnl_reconciled": False,
        "execution_authorized": False,
        "orders_sent": False,
        "production_ready": False,
    }


def hypothetical_position_funding(*, audit_report, rows_by_symbol,
                                  symbol, side, quantity,
                                  entry_ms, exit_ms):
    """Compute hypothetical settlement cashflow when complete series supplied.

    Treat a settlement EXACTLY at entry/exit as indeterminate without order
    sequencing evidence; never invent a charge or credit. Funding cashflow
    is -position_direction * quantity * settlement_mark * funding_rate.
    """
    if not isinstance(audit_report, dict) or (
        audit_report.get("status") != "FUNDING_CONTINUITY_COMPLETE_UNAUTHENTICATED"
    ):
        return {"status": "UNKNOWN_FUNDING", "reason": "funding_audit_incomplete",
                "orders_sent": False}
    if symbol not in COINS or side not in ("long", "short"):
        raise ValueError("invalid_funding_position")
    qty = _d(quantity, positive=True)
    if (not _time(entry_ms) or not _time(exit_ms) or
            entry_ms >= exit_ms or
            entry_ms < audit_report.get("window_start_ms", 0) or
            exit_ms >= audit_report.get("window_end_exclusive_ms", 0)):
        raise ValueError("funding_position_outside_history")
    if not isinstance(rows_by_symbol, dict) or set(rows_by_symbol) != set(COINS):
        raise ValueError("four_explicit_funding_symbols_required")
    symbol_report = audit_report.get("symbols", {}).get(symbol, {})
    if symbol_report.get("status") != "COMPLETE_UNAUTHENTICATED":
        return {"status": "UNKNOWN_FUNDING", "reason": "symbol_funding_incomplete",
                "orders_sent": False}
    parsed = _validate_rows(rows_by_symbol[symbol],
                            audit_report["window_start_ms"],
                            audit_report["window_end_exclusive_ms"])
    if _fingerprint(parsed) != symbol_report.get("funding_sha256"):
        return {"status": "UNKNOWN_FUNDING", "reason": "audited_funding_changed",
                "orders_sent": False}
    if any(t == entry_ms or t == exit_ms for t, _, _ in parsed):
        return {"status": "UNKNOWN_FUNDING", "reason": "ambiguous_settlement_boundary",
                "orders_sent": False}
    sign = Decimal("-1") if side == "long" else Decimal("1")
    amounts = [sign * qty * mark * rate
               for t, rate, mark in parsed if entry_ms < t < exit_ms]
    return {
        "status": "HYPOTHETICAL_FUNDING_ONLY",
        "funding_pnl_usdt_unverified": str(sum(amounts, Decimal("0"))),
        "settlements_in_position": len(amounts),
        "funding_reconciled": False,
        "source_independently_authenticated": False,
        "orders_sent": False,
        "execution_authorized": False,
    }
