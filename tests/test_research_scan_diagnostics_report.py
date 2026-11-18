"""Offline tests for research scan diagnostic aggregation."""
import pytest
from futures_engine.research_scan_diagnostics_report import summarize_scan_diagnostics


def scan(symbol, *, setups=0, low=0, invalid=0, rejected=0, eligible=0):
    return {
        "symbol": symbol, "status": "RESEARCH_ONLY",
        "scan_diagnostics": {
            "setups_seen": setups, "below_threshold": low,
            "invalid_score": invalid, "verification_rejected": rejected,
            "eligible": eligible, "no_setup": setups == 0,
        },
    }


def test_counts_scans_and_setups_separately():
    report = summarize_scan_diagnostics([
        scan("SOL", setups=3, low=1, rejected=1, eligible=1),
        scan("SOL"), scan("XRP", setups=2, invalid=2),
    ])
    assert report["totals"]["scans"] == 3
    assert report["totals"]["setups_seen"] == 5
    assert report["totals"]["no_setup_scans"] == 1
    assert report["by_symbol"]["SOL"]["eligible"] == 1
    assert report["by_symbol"]["XRP"]["invalid_score"] == 2
    assert report["execution_authorized"] is False


def test_legacy_scan_not_falsely_classified_as_no_setup():
    report = summarize_scan_diagnostics([
        {"symbol": "SOL", "status": "RESEARCH_ONLY"},
        scan("SOL"),
    ])
    assert report["totals"]["legacy_scans_without_diagnostics"] == 1
    assert report["totals"]["no_setup_scans"] == 1


def test_blocked_scan_is_counted_separately():
    report = summarize_scan_diagnostics([
        {"symbol": "XRP", "status": "BLOCKED"},
    ])
    assert report["totals"]["blocked_scans"] == 1
    assert report["totals"]["legacy_scans_without_diagnostics"] == 1


@pytest.mark.parametrize("diagnostics", [
    {"setups_seen": 1, "below_threshold": 0, "invalid_score": 0,
     "verification_rejected": 0, "eligible": 0, "no_setup": False},
    {"setups_seen": -1, "below_threshold": 0, "invalid_score": 0,
     "verification_rejected": 0, "eligible": 0, "no_setup": False},
    {"setups_seen": 0, "below_threshold": 0, "invalid_score": 0,
     "verification_rejected": 0, "eligible": 0, "no_setup": False},
])
def test_inconsistent_counts_fail_closed(diagnostics):
    with pytest.raises(ValueError):
        summarize_scan_diagnostics([{
            "symbol": "SOL", "status": "RESEARCH_ONLY",
            "scan_diagnostics": diagnostics,
        }])
