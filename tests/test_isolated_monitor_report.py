"""Offline-only tests for isolated monitor evidence reporting."""
import json
from tools.isolated_monitor_report import summarize


def test_counts_and_blocked_85_candidates_without_claiming_execution():
    rows = [
        {"event": "scan", "at": 100, "symbol": "BTC/USDT:USDT", "qualified": 1, "orders_sent": 0, "telegram_sent": 0},
        {"event": "candidate", "at": 100, "score": 85, "blocked": True, "block_condition": "no_independent_demo_order_authorization"},
        {"event": "candidate", "at": 101, "score": 80, "blocked": True, "block_condition": "no_independent_demo_order_authorization"},
        {"event": "condition", "at": 102, "strategy": "EMA_ADX", "name": "adx", "passed": False},
        {"event": "heartbeat", "at": 103, "mode": "read_only", "telegram_sent": False},
    ]
    report = summarize([json.dumps(x) for x in rows])
    assert report["records"] == 5
    assert report["candidate_count"] == 2
    assert report["candidate_at_least_85"] == 1
    assert report["eligible_candidates_blocked"] == 1
    assert report["blocked_by_reason"]["no_independent_demo_order_authorization"] == 2
    assert report["failed_conditions"] == {"EMA_ADX:adx": 1}
    assert report["scan_qualified_count"] == 1
    assert report["telegram_sent_events"] == 0
    assert report["orders_sent_count"] == 0
    assert report["e2e_verified"] is False


def test_malformed_and_boolean_counts_fail_closed():
    report = summarize([
        "not-json", "[]", json.dumps({"event": "scan", "qualified": True, "orders_sent": True, "telegram_sent": False}),
        json.dumps({"event": "candidate", "score": True, "blocked": True}),
        json.dumps({"event": "candidate", "score": 88, "blocked": False}),
    ])
    assert report["malformed"] == 2
    assert report["scan_qualified_count"] == 0
    assert report["orders_sent_count"] == 0
    assert report["candidate_at_least_85"] == 1
    assert report["eligible_candidates_blocked"] == 0
