"""Offline combined coverage report. Never upgrades integrity into authenticity."""
from signals_v3.funding_coverage_audit import audit_funding_coverage
from signals_v3.orderbook_coverage_audit import audit_orderbook_coverage


def audit_historical_market_coverage(
    funding_records, funding_event_times, orderbook_samples,
    decision_times, symbol, max_orderbook_age_ms,
):
    funding = audit_funding_coverage(funding_records, funding_event_times, symbol)
    orderbook = audit_orderbook_coverage(
        orderbook_samples, decision_times, symbol, max_orderbook_age_ms
    )
    complete = (
        funding["funding_coverage_complete"]
        and orderbook["orderbook_coverage_complete"]
    )
    return {
        "symbol": symbol,
        "funding": funding,
        "orderbook": orderbook,
        "combined_integrity_coverage_complete": complete,
        # The two independent source-authenticity requirements are still open.
        "historical_evidence_verified": False,
        "funding_history_verified": False,
        "orderbook_history_verified": False,
        "provider_authenticity_verified": False,
        "research_readiness": "awaiting_provider_authenticated_evidence",
    }
