"""Offline-only 90-day Binance USDT-M OHLCV completeness gate.

This module has NO network/exchange imports, does not fetch history or place
orders, and does not authenticate historical data. A self-declared Binance
source, or a content SHA256, is NOT independent source provenance.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json

COINS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT")
INTERVAL_MS = 300_000
DAYS = 90
TRAIN_DAYS = 63
TEST_DAYS = 27
MAX_EVAL_BARS = 48
EXPECTED_BARS = DAYS * 24 * 12


def _at_utc_midnight(day):
    if not isinstance(day, str):
        raise ValueError("invalid_utc_day")
    parsed = date.fromisoformat(day)
    if parsed.isoformat() != day:
        raise ValueError("invalid_utc_day")
    return int(datetime(parsed.year, parsed.month, parsed.day,
                        tzinfo=timezone.utc).timestamp() * 1000)


def _price(value):
    if isinstance(value, bool):
        raise ValueError("invalid_price")
    try:
        n = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("invalid_price") from exc
    if not n.is_finite() or n <= 0:
        raise ValueError("invalid_price")
    return n


def _check_candles(rows, start_ms, end_ms, closed_through_ms):
    """Return diagnostics, never count incomplete or malformed data as ready."""
    if not isinstance(rows, (list, tuple)):
        return {"status": "MISSING", "observed_bars": 0,
                "expected_bars": EXPECTED_BARS}
    n = len(rows)
    report = {"status": "INCOMPLETE", "observed_bars": n,
              "expected_bars": EXPECTED_BARS}
    if n != EXPECTED_BARS:
        report["reason"] = "incorrect_closed_candle_count"
        return report
    digest = sha256()
    for offset, row in enumerate(rows):
        if (not isinstance(row, (list, tuple)) or len(row) != 5
                or type(row[0]) is not int):
            return {**report, "reason": "invalid_candle"}
        at = start_ms + offset * INTERVAL_MS
        if row[0] != at or at + INTERVAL_MS > closed_through_ms or at >= end_ms:
            return {**report, "reason": "timestamp_gap_duplicate_or_unclosed",
                    "first_bad_offset": offset}
        try:
            opening, high, low, close = map(_price, row[1:])
        except ValueError:
            return {**report, "reason": "invalid_candle_prices",
                    "first_bad_offset": offset}
        if high < max(opening, close, low) or low > min(opening, close, high):
            return {**report, "reason": "invalid_candle_range",
                    "first_bad_offset": offset}
        canonical = [at] + [str(x) for x in (opening, high, low, close)]
        digest.update(json.dumps(canonical, separators=(",", ":")).encode("ascii"))
        digest.update(b"\n")
    return {**report, "status": "COMPLETE_UNAUTHENTICATED",
            "reason": "integrity_only_no_upstream_authentication",
            "history_sha256": digest.hexdigest()}


def inspect_90_days(*, start_day, candles_by_symbol, provenance_by_symbol,
                    evaluated_as_of_ms, max_evaluation_bars=MAX_EVAL_BARS):
    """Check exactly 90 full UTC days for four symbols and lock a 70/30 split.

    The 63-day training section cannot evaluate a trade using the test period:
    a trade's entry opens one bar after its signal and may use at most
    max_evaluation_bars fully closed bars. Candidate signal time must be no
    later than the last eligible signal open returned below.

    Funding, actual fills and source authentication MUST be verified by other
    independent modules. Therefore this gate never returns 'production_ready'.
    """
    start_ms = _at_utc_midnight(start_day)
    if type(evaluated_as_of_ms) is not int or evaluated_as_of_ms <= 0:
        raise ValueError("invalid_as_of_time")
    if (type(max_evaluation_bars) is not int or
            not 1 <= max_evaluation_bars <= MAX_EVAL_BARS):
        raise ValueError("invalid_evaluation_horizon")
    if not isinstance(candles_by_symbol, dict) or not isinstance(provenance_by_symbol, dict):
        raise ValueError("missing_data_maps")
    if set(candles_by_symbol) != set(COINS) or set(provenance_by_symbol) != set(COINS):
        raise ValueError("four_explicit_futures_symbols_required")

    end_ms = start_ms + DAYS * 86_400_000
    split_ms = start_ms + TRAIN_DAYS * 86_400_000
    if evaluated_as_of_ms < end_ms:
        raise ValueError("incomplete_full_utc_days")
    details = {}
    for coin in COINS:
        provenance = provenance_by_symbol[coin]
        if not isinstance(provenance, dict):
            details[coin] = {"status": "UNVERIFIED_PROVENANCE"}
            continue
        if (provenance.get("exchange") != "BINANCE" or
                provenance.get("market") != "USDT_M_FUTURES" or
                provenance.get("interval") != "5m"):
            details[coin] = {"status": "UNVERIFIED_PROVENANCE",
                             "reason": "exchange_market_interval_mismatch"}
            continue
        fetched = provenance.get("fetched_at_ms")
        closed = provenance.get("closed_through_ms")
        if (type(fetched) is not int or type(closed) is not int or
                closed % INTERVAL_MS or fetched < end_ms or
                fetched > evaluated_as_of_ms or closed > fetched or
                closed < end_ms):
            details[coin] = {"status": "UNVERIFIED_PROVENANCE",
                             "reason": "unverified_or_incomplete_timestamps"}
            continue
        details[coin] = _check_candles(candles_by_symbol[coin],
                                       start_ms, end_ms, closed)

    complete = all(row.get("status") == "COMPLETE_UNAUTHENTICATED"
                   for row in details.values())
    return {
        "status": "OHLCV_CONTINUITY_COMPLETE_PROVENANCE_UNAUTHENTICATED"
                  if complete else "NOT_ENOUGH_VERIFIED_HISTORY",
        "symbols": details,
        "window_start_utc": start_day,
        "window_end_exclusive_ms": end_ms,
        "expected_days": DAYS,
        "bars_per_symbol": EXPECTED_BARS,
        "train_days": TRAIN_DAYS,
        "test_days": TEST_DAYS,
        "split_utc_ms": split_ms,
        "last_eligible_train_signal_open_ms":
            split_ms - (max_evaluation_bars + 1) * INTERVAL_MS,
        "first_eligible_test_signal_open_ms": split_ms,
        "last_eligible_test_signal_open_ms":
            end_ms - (max_evaluation_bars + 1) * INTERVAL_MS,
        "max_evaluation_bars": max_evaluation_bars,
        "train_test_leakage_guard": True,
        "funding_reconciled": False,
        "source_independently_authenticated": False,
        "live_fills_reconciled": False,
        "execution_authorized": False,
        "orders_sent": False,
        "production_ready": False,
    }
