"""Offline tests of the existing exchange-verified attribution adapter."""
import demo_attribution_summary as summary
import pytest


def report(owned=2, unknown=3):
    return dict(status="AUDIT_ONLY_NOT_EXECUTABLE",
                execution_authorized=False, allocation_ledger_reconciled=False,
                risk_snapshot_approved=False,
                scope="four_symbols_only_funding_and_other_symbols_not_reconciled",
                signalpilot_fills=owned,
                unattributed_fills=unknown)


def test_summary_never_authorizes(monkeypatch):
    monkeypatch.setattr(summary, "audit", lambda *a, **kw: report())
    result = summary.summarize_verified_attribution(object(), registry_path="unused")
    assert result["verified_signalpilot_fills"] == 2
    assert result["unattributed_fills"] == 3
    assert result["historical_reconciliation_complete"] is False
    assert result["execution_authorized"] is False


def test_rejects_unexpected_authorization(monkeypatch):
    data = report()
    data["execution_authorized"] = True
    monkeypatch.setattr(summary, "audit", lambda *a, **kw: data)
    with pytest.raises(ValueError, match="unexpected_execution_authorization"):
        summary.summarize_verified_attribution(object(), registry_path="unused")


def test_rejects_invalid_counts(monkeypatch):
    monkeypatch.setattr(summary, "audit", lambda *a, **kw: report(unknown=-1))
    with pytest.raises(ValueError, match="invalid_attribution_counts"):
        summary.summarize_verified_attribution(object(), registry_path="unused")


def test_rejects_untrusted_scope(monkeypatch):
    data = report()
    data["scope"] = "all_symbols_reconciled"
    monkeypatch.setattr(summary, "audit", lambda *a, **kw: data)
    with pytest.raises(ValueError, match="untrusted_attribution_scope"):
        summary.summarize_verified_attribution(object(), registry_path="unused")


def test_rejects_risk_approval(monkeypatch):
    data = report()
    data["risk_snapshot_approved"] = True
    monkeypatch.setattr(summary, "audit", lambda *a, **kw: data)
    with pytest.raises(ValueError, match="unexpected_risk_approval"):
        summary.summarize_verified_attribution(object(), registry_path="unused")
