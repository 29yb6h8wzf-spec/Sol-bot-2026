"""Offline score diagnostics do not loosen the 85-point execution gate."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from research.paper_signal_diagnostics import diagnose_snapshot
from research.paper_filter_audit import audit_filters
from futures_engine.verified_strategy_scan import to_strategy_candles

SNAPSHOT = Path(__file__).parent / "fixtures" / "forward_connector_snapshot_20261109_2023utc.json"


def _payload():
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_real_forward_snapshot_reports_all_thresholds_without_orders():
    report = diagnose_snapshot(_payload())
    assert report["status"] == "OFFLINE_DIAGNOSTICS_ONLY"
    assert report["orders_sent"] is False
    assert len(report["reports"]) == 2
    for symbol in report["reports"]:
        counts = symbol["counts_by_threshold"]
        assert set(counts) == {"70", "75", "80", "85"}
        assert counts["70"] >= counts["75"] >= counts["80"] >= counts["85"]
        assert counts["85"] == 0
        assert symbol["execution_authorized"] is False
        print(json.dumps(symbol, sort_keys=True))


def test_diagnostics_rejects_unclosed_or_missing_market_data():
    payload = _payload()
    payload["items"][0]["five"][-1][0] += 300000
    with pytest.raises(ValueError, match="unclosed|noncontiguous"):
        diagnose_snapshot(payload)


def test_each_strategy_side_has_actual_threshold_and_pass_fail_evidence():
    report = diagnose_snapshot(_payload())
    expected = {
        ("EMA_ADX", "LONG"), ("EMA_ADX", "SHORT"),
        ("RSI_BOLL", "LONG"), ("RSI_BOLL", "SHORT"),
        ("MACD_VOLUME", "LONG"), ("MACD_VOLUME", "SHORT"),
    }
    for item in report["reports"]:
        gates = item["filter_audit"]
        assert len(gates) == 6
        assert {(x["strategy"], x["direction"]) for x in gates} == expected
        assert item["filter_pass_count"] == 0
        for entry in gates:
            assert entry["passed"] is False
            assert entry["failed_filters"]
            assert entry["failed_filters"] == [
                x["name"] for x in entry["conditions"] if not x["passed"]
            ]
            assert all(
                isinstance(x["actual"], (float, int))
                and isinstance(x["threshold"], (float, int))
                and type(x["passed"]) is bool
                for x in entry["conditions"]
            )
        print(json.dumps({
            "symbol": item["symbol"],
            "blockers": [
                {"strategy": x["strategy"], "direction": x["direction"],
                 "failed_filters": x["failed_filters"]}
                for x in gates
            ],
        }, sort_keys=True))


def test_filter_audit_fails_closed_if_strategy_implementation_drifts():
    item = _payload()["items"][0]
    five = to_strategy_candles(item["five"])
    four = to_strategy_candles(item["four"])
    with (patch("research.paper_filter_audit.candidates",
                return_value=([{"strategy": "EMA_ADX", "direction": "LONG"}], {})),
          pytest.raises(ValueError, match="strategy filter audit drift")):
        audit_filters(five, four)
