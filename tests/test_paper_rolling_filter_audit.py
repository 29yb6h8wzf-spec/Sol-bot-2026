"""Rolling research uses only data closed at each decision timestamp."""
import json
from pathlib import Path

import pytest

from research.paper_rolling_filter_audit import rolling_filter_report

FIXTURES = Path(__file__).parent / "fixtures"


def _xrp():
    return json.loads((FIXTURES / "xrpusdt_verified_20261109.json").read_text())


def test_real_xrp_rolling_audit_finds_verified_historical_90_setup():
    data = _xrp()
    result = rolling_filter_report(
        data["five"], data["four"], symbol=data["symbol"],
        asof_ms=data["asof_ms"],
    )
    assert result["status"] == "HISTORICAL_IN_SAMPLE_FILTER_AUDIT"
    assert result["orders_sent"] is False
    assert result["out_of_sample"] is False
    assert result["counts"]["scans"] > 50
    assert result["counts"]["setups_85_plus"] >= 1
    assert any(
        s["strategy"] == "EMA_ADX"
        and s["direction"] == "SHORT"
        and s["score"] >= 85
        for s in result["scans"][-1]["setups_85_plus"]
    )
    assert all(
        row["four_hour_last_closed_ms"] <= row["candle_ms"] + 300000
        for row in result["scans"]
    )
    print(json.dumps({
        "symbol": result["symbol"], "counts": result["counts"],
        "filter_pass_rates": result["filter_pass_rates"],
    }, sort_keys=True))


def test_rolling_audit_does_not_look_ahead_at_later_5m_or_4h_bars():
    data = _xrp()
    full = rolling_filter_report(
        data["five"], data["four"], symbol=data["symbol"],
        asof_ms=data["asof_ms"],
    )
    truncated = rolling_filter_report(
        data["five"][:200], data["four"], symbol=data["symbol"],
        asof_ms=data["five"][199][0] + 300000,
    )
    assert truncated["scans"] == full["scans"][:len(truncated["scans"])]
    assert truncated["counts"]["scans"] == len(truncated["scans"])


def test_rolling_audit_rejects_unclosed_or_gapped_history():
    data = _xrp()
    with pytest.raises(ValueError, match="unclosed"):
        rolling_filter_report(
            data["five"], data["four"], symbol=data["symbol"],
            asof_ms=data["asof_ms"] - 300000,
        )
    broken = data["five"].copy()
    broken.pop(150)
    with pytest.raises(ValueError, match="noncontiguous"):
        rolling_filter_report(
            broken, data["four"], symbol=data["symbol"],
            asof_ms=data["asof_ms"],
        )


def test_real_sol_and_xrp_forward_snapshot_rolling_audit_is_descriptive():
    data = json.loads((
        FIXTURES / "forward_connector_snapshot_20261109_2023utc.json"
    ).read_text())
    for item in data["items"]:
        report = rolling_filter_report(
            item["five"], item["four"], symbol=item["symbol"],
            asof_ms=data["captured_at_ms"],
        )
        assert report["counts"]["scans"] > 50
        assert report["orders_sent"] is False
        assert report["profitable_claim"] is False
        assert report["out_of_sample"] is False
        print(json.dumps({
            "symbol": report["symbol"], "counts": report["counts"],
        }, sort_keys=True))
