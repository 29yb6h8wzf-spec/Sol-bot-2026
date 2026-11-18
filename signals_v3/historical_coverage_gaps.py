"""Deterministic JSON-safe gap summary for offline historical coverage.

Consumes the existing combined audit output. Does not acquire data or
authenticate exchange/provider sources.
"""
import json


def summarize_historical_coverage(report):
    if type(report) is not dict or type(report.get("funding")) is not dict or type(report.get("orderbook")) is not dict:
        raise ValueError("invalid_historical_coverage_report")
    funding = report["funding"]
    book = report["orderbook"]
    keys = ("missing_event_times", "duplicate_event_times", "unexpected_event_times")
    book_keys = ("missing_decisions", "stale_decisions")
    if any(type(funding.get(k)) not in (tuple, list) for k in keys) or any(
        type(book.get(k)) not in (tuple, list) for k in book_keys
    ):
        raise ValueError("invalid_historical_coverage_report")
    if type(report.get("symbol")) is not str or not report["symbol"]:
        raise ValueError("invalid_historical_coverage_report")
    gaps = {
        "funding_missing": list(funding["missing_event_times"]),
        "funding_duplicate": list(funding["duplicate_event_times"]),
        "funding_unexpected": list(funding["unexpected_event_times"]),
        "orderbook_missing": list(book["missing_decisions"]),
        "orderbook_stale": list(book["stale_decisions"]),
    }
    if any(type(t) is not int or t < 0 for values in gaps.values() for t in values):
        raise ValueError("invalid_historical_coverage_report")
    gaps = {key: sorted(set(values)) for key, values in gaps.items()}
    return {
        "schema_version": 1,
        "symbol": report["symbol"],
        "gap_counts": {key: len(values) for key, values in gaps.items()},
        "gap_timestamps_ms": gaps,
        "integrity_coverage_complete": all(not values for values in gaps.values()),
        "historical_evidence_verified": False,
        "provider_authenticity_verified": False,
        "funding_history_verified": False,
        "orderbook_history_verified": False,
        "readiness": "blocked_pending_provider_authenticated_evidence",
    }


def historical_coverage_report_json(report):
    return json.dumps(summarize_historical_coverage(report), sort_keys=True, indent=2)
