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


def classify_historical_signal(signal_candle_open_ms, coverage_report):
    """Return train/test/embargo eligibility for a 5m signal OPEN timestamp.

    This is a pure, offline split classifier. It never creates a trade or
    accepts missing history as evidence. The split is meaningful only after
    all four sources pass the (still unauthenticated) OHLC continuity checks.
    """
    if type(signal_candle_open_ms) is not int or signal_candle_open_ms < 0:
        raise ValueError("invalid_signal_timestamp")
    if signal_candle_open_ms % INTERVAL_MS:
        raise ValueError("unaligned_signal_timestamp")
    if not isinstance(coverage_report, dict):
        raise ValueError("invalid_coverage_report")
    if coverage_report.get("status") != (
            "OHLCV_CONTINUITY_COMPLETE_PROVENANCE_UNAUTHENTICATED"):
        return {"status": "BLOCKED_INCOMPLETE_DATA", "orders_sent": False}
    split = coverage_report.get("split_utc_ms")
    end = coverage_report.get("window_end_exclusive_ms")
    start = _at_utc_midnight(coverage_report.get("window_start_utc"))
    last_train = coverage_report.get("last_eligible_train_signal_open_ms")
    last_test = coverage_report.get("last_eligible_test_signal_open_ms")
    max_bars = coverage_report.get("max_evaluation_bars")
    if (type(split) is not int or type(end) is not int or
            type(last_train) is not int or type(last_test) is not int or
            type(max_bars) is not int or
            max_bars <= 0 or max_bars > MAX_EVAL_BARS or
            split != start + TRAIN_DAYS * 86_400_000 or
            end != start + DAYS * 86_400_000 or
            last_train != split - (max_bars + 1) * INTERVAL_MS or
            last_test != end - (max_bars + 1) * INTERVAL_MS):
        raise ValueError("invalid_split_boundaries")
    if signal_candle_open_ms < start or signal_candle_open_ms > last_test:
        section = "EXCLUDED_OUTSIDE_FULL_WINDOW"
    elif signal_candle_open_ms <= last_train:
        section = "OFFLINE_TRAIN_ONLY"
    elif signal_candle_open_ms < split:
        section = "EXCLUDED_TRAIN_TEST_EMBARGO"
    else:
        section = "OFFLINE_TEST_ONLY"
    return {"status": section, "orders_sent": False,
            "execution_authorized": False,
            "source_independently_authenticated": False}
