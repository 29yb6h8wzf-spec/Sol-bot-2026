"""Fail-closed provenance gate for historical dynamic-universe evidence.

Current public snapshots cannot be passed off as historical depth/spread evidence.
"""
import json
from pathlib import Path

def verify_historical_evidence_manifest(path,decision_ms):
    manifest=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(manifest,dict):
        raise ValueError("invalid_historical_evidence_manifest")
    if manifest.get("current_only") is not False or manifest.get("historical_universe_verified") is not True:
        raise ValueError("unverified_historical_universe_provenance")
    if manifest.get("source_type") not in ("archived_orderbook_snapshots","historical_market_data_provider"):
        raise ValueError("unsupported_historical_evidence_source")
    if not isinstance(decision_ms,int) or isinstance(decision_ms,bool) or decision_ms<0:
        raise ValueError("invalid_decision_timestamp")
    start=manifest.get("coverage_start_ms")
    end=manifest.get("coverage_end_ms")
    if any(not isinstance(v,int) or isinstance(v,bool) for v in (start,end)) or start>end or not start<=decision_ms<=end:
        raise ValueError("historical_evidence_outside_coverage")
    if not manifest.get("source_reference") or not isinstance(manifest["source_reference"],str):
        raise ValueError("missing_historical_evidence_source_reference")
    if manifest.get("point_in_time_listings_verified") is not True or manifest.get("spread_and_depth_verified") is not True:
        raise ValueError("incomplete_historical_evidence")
    return {"decision_ms":decision_ms,"historical_evidence_verified":True,
            "source_type":manifest["source_type"]}
