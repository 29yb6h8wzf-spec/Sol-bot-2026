"""Strict offline point-in-time universe replay. No trading connectivity.

Every decision must carry a complete historical market listing and a complete
same-decision observation set. Missing periods fail closed, not forward-filled.
"""
from signals_v3.historical_universe_gate import verify_decision_snapshot

def replay_universe(decisions):
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
        result=verify_decision_snapshot(
            decision["observations"],timestamp,decision["expected_symbols"])
        current_listing=frozenset(decision["expected_symbols"])
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
    return tuple(output)
