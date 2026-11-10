"""Persist prospective public-market research captures without historical claims.

Append-only JSONL: existing records are never silently overwritten.
No exchange calls, credentials, orders, or deployment.
"""
import json
from pathlib import Path

def append_current_capture(path,capture):
    if not isinstance(capture,dict) or capture.get("current_only") is not True or capture.get("historical_universe_verified") is not False:
        raise ValueError("invalid_current_capture_provenance")
    if not isinstance(capture.get("snapshots"),list) or capture.get("captured_count")!=len(capture["snapshots"]):
        raise ValueError("invalid_capture_count")
    if capture.get("complete_market_capture") is True and capture.get("candidate_count")!=capture["captured_count"]:
        raise ValueError("false_complete_market_claim")
    if not isinstance(capture.get("candidate_count"),int) or capture["candidate_count"]<capture["captured_count"]:
        raise ValueError("invalid_candidate_count")
    symbols=[]
    for snapshot in capture["snapshots"]:
        if snapshot.get("current_only") is not True or snapshot.get("historical_universe_verified") is not False:
            raise ValueError("invalid_snapshot_provenance")
        if not isinstance(snapshot.get("observed_at_ms"),int) or snapshot["observed_at_ms"]<0:
            raise ValueError("invalid_snapshot_timestamp")
        symbols.append(snapshot["symbol"])
    if len(symbols)!=len(set(symbols)):
        raise ValueError("duplicate_snapshot_symbols")
    target=Path(path)
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("a",encoding="utf-8") as handle:
        handle.write(json.dumps(capture,sort_keys=True,allow_nan=False)+"\n")
    return {"path":str(target),"appended":1,"captured_count":len(symbols),
            "complete_market_capture":capture.get("complete_market_capture") is True}
