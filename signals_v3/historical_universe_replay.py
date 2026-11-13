"""Strict offline point-in-time universe replay. No trading connectivity.

Every decision must carry a complete historical market listing and a complete
same-decision observation set. Missing periods fail closed, not forward-filled.
"""
from signals_v3.historical_universe_gate import verify_decision_snapshot

def replay_universe(decisions, expected_decision_times=None):
    """Replay decisions; strict callers should use replay_complete_universe."""
    if expected_decision_times is not None:
        # The audit schedule must be materialized before validation. Lazy feeds
        # can fail midway or change between passes, undermining replay coverage.
        if type(expected_decision_times) not in (tuple, list):
            raise ValueError("invalid_expected_decision_schedule")
        expected_decision_times=tuple(expected_decision_times)
        if not expected_decision_times or any(not isinstance(t,int) or isinstance(t,bool) or t<0 for t in expected_decision_times):
            raise ValueError("invalid_expected_decision_schedule")
        if any(b<=a for a,b in zip(expected_decision_times,expected_decision_times[1:])):
            raise ValueError("invalid_expected_decision_schedule")
    # An audit decision grid must be fully materialized before replay. A lazy
    # source can truncate after yielding plausible early snapshots.
    if type(decisions) not in (tuple, list):
        raise ValueError("invalid_historical_decision_container")
    output=[]
    previous=None
    previous_listing=None
    for decision in decisions:
        if not isinstance(decision,dict):
            raise ValueError("invalid_replay_decision")
        timestamp=decision.get("decision_ms")
        if not isinstance(timestamp,int) or isinstance(timestamp,bool) or timestamp<0:
            raise ValueError("invalid_decision_timestamp")
        if previous is not None and timestamp<=previous:
            raise ValueError("nonmonotonic_decision_times")
        if "observations" not in decision or "expected_symbols" not in decision:
            raise ValueError("missing_historical_evidence")
        # Preserve the gate's strict materialized-listing contract. Coercing
        # generators here would bypass its rejection of lazy historical evidence.
        listing=decision["expected_symbols"]
        if type(listing) not in (list,tuple):
            raise ValueError("invalid_historical_market_listing")
        result=verify_decision_snapshot(
            decision["observations"],timestamp,listing)
        current_listing=frozenset(listing)
        if previous_listing is not None:
            result["listed_added"]=tuple(sorted(current_listing-previous_listing))
            result["listed_removed"]=tuple(sorted(previous_listing-current_listing))
        else:
            result["listed_added"]=()
            result["listed_removed"]=()
        if len(result["eligible_symbols"])>len(current_listing):
            raise ValueError("universe_integrity_failure")
        output.append(result)
        previous=timestamp
        previous_listing=current_listing
    if not output:
        raise ValueError("empty_historical_replay")
    if expected_decision_times is not None and tuple(r["decision_ms"] for r in output)!=expected_decision_times:
        raise ValueError("incomplete_historical_decision_schedule")
    return tuple(output)


def replay_complete_universe(decisions, expected_decision_times):
    """Production research entry point: never allow an implicit schedule."""
    if expected_decision_times is None:
        raise ValueError("missing_expected_decision_schedule")
    return replay_universe(decisions, expected_decision_times)


def replay_verified_historical_universe(decisions, expected_decision_times, evidence_manifest_path):
    """Require independently hashed historical listing and order-book artifacts.

    A complete observation grid alone is not proof that observations are historical.
    Validate provenance at every requested decision timestamp before replay.
    """
    from signals_v3.historical_evidence_provenance import verify_historical_evidence_manifest
    if expected_decision_times is None:
        raise ValueError("missing_expected_decision_schedule")
    # Reject lazy decision feeds before opening any provenance artifact. The
    # verified entry point must enforce the same materialization contract.
    if type(decisions) not in (tuple, list):
        raise ValueError("invalid_historical_decision_container")
    # Do not materialize lazy schedules before validating their provenance.
    # A truncated iterator could otherwise be mistaken for a complete audit grid.
    if type(expected_decision_times) not in (tuple, list):
        raise ValueError("invalid_expected_decision_schedule")
    schedule=tuple(expected_decision_times)
    if (not schedule or any(type(t) is not int or t < 0 for t in schedule)
            or any(b <= a for a, b in zip(schedule, schedule[1:]))):
        raise ValueError("invalid_expected_decision_schedule")
    if not evidence_manifest_path:
        raise ValueError("missing_historical_evidence_manifest")
    for timestamp in schedule:
        verification=verify_historical_evidence_manifest(evidence_manifest_path,timestamp)
        if verification.get("historical_evidence_verified") is not True:
            raise ValueError("unverified_historical_evidence")
        if any(verification.get(field) is not True for field in (
            "provider_authenticity_verified", "historical_market_coverage_verified",
            "funding_history_verified", "orderbook_history_verified",
            "point_in_time_universe_verified")):
            raise ValueError("incomplete_historical_evidence")
    return replay_complete_universe(decisions,schedule)
