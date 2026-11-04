"""Read-only adapter for the existing Binance DEMO attribution audit.

The exchange provenance check MUST run inside demo_trade_attribution.audit.
This adapter never treats an unconfirmed local registry row as proof.
"""
from demo_trade_attribution import audit


def summarize_verified_attribution(exchange, *, registry_path, now_ms=None):
    report = audit(exchange, registry_path=registry_path, now_ms=now_ms)
    if report.get("status") != "AUDIT_ONLY_NOT_EXECUTABLE":
        raise ValueError("untrusted_attribution_status")
    if report.get("execution_authorized") is not False:
        raise ValueError("unexpected_execution_authorization")
    if report.get("scope") != "four_symbols_only_funding_and_other_symbols_not_reconciled":
        raise ValueError("untrusted_attribution_scope")
    if report.get("allocation_ledger_reconciled") is not False:
        raise ValueError("unexpected_allocation_reconciliation")
    if report.get("risk_snapshot_approved") is not False:
        raise ValueError("unexpected_risk_approval")
    owned = report.get("signalpilot_fills")
    unknown = report.get("unattributed_fills")
    if any(type(n) is not int or n < 0 for n in (owned, unknown)):
        raise ValueError("invalid_attribution_counts")
    return {"status": "AUDIT_ONLY_NOT_EXECUTABLE",
            "verified_signalpilot_fills": owned,
            "unattributed_fills": unknown,
            "historical_reconciliation_complete": False,
            "allocation_ledger_reconciled": False,
            "execution_authorized": False,
            "orders_sent": False}
