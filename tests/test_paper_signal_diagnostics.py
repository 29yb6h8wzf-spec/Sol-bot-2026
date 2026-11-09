"""Offline score diagnostics do not loosen the 85-point execution gate."""
import json
from pathlib import Path

import pytest

from research.paper_signal_diagnostics import diagnose_snapshot

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
