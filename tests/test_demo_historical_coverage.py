from demo_historical_coverage import coverage
import pytest


def test_missing_days_never_become_clean():
    result = coverage("2026-11-01", "2026-11-03", {})
    assert len(result["days"]) == 3
    assert all(day["status"] == "MISSING" for day in result["days"])
    assert result["reconciled"] is False
    assert result["execution_authorized"] is False


def test_partial_audit_does_not_clear_history():
    report = {"status": "AUDIT_ONLY_NOT_EXECUTABLE",
              "execution_authorized": False}
    result = coverage("2026-11-01", "2026-11-02", {"2026-11-01": report})
    assert result["days"][0]["status"] == "PARTIAL_AUDIT"
    assert result["days"][1]["status"] == "MISSING"
    assert result["reconciled"] is False


def test_rejects_authorized_report():
    with pytest.raises(ValueError, match="untrusted_report"):
        coverage("2026-11-01", "2026-11-01",
                 {"2026-11-01": {"status": "AUDIT_ONLY_NOT_EXECUTABLE",
                                  "execution_authorized": True}})


def test_rejects_unbounded_window():
    with pytest.raises(ValueError, match="invalid_window"):
        coverage("2026-01-01", "2026-11-04", {})
