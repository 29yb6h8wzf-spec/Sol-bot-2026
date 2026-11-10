"""Fail-closed provenance gate for historical dynamic-universe evidence.

Current public snapshots cannot be passed off as historical depth/spread evidence.
"""
import json
import hashlib
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
    if any(not isinstance(v,int) or isinstance(v,bool) for v in (start,end)) or start<0 or end<0 or start>end or not start<=decision_ms<=end:
        raise ValueError("historical_evidence_outside_coverage")
    if not isinstance(manifest.get("source_reference"),str) or not manifest["source_reference"].strip():
        raise ValueError("missing_historical_evidence_source_reference")
    if manifest.get("point_in_time_listings_verified") is not True or manifest.get("spread_and_depth_verified") is not True:
        raise ValueError("incomplete_historical_evidence")
    artifacts=manifest.get("evidence_artifacts")
    if not isinstance(artifacts,list) or not artifacts:
        raise ValueError("missing_verifiable_historical_artifacts")
    verified_roles=set()
    seen_paths=set()
    root=Path(path).resolve().parent
    for item in artifacts:
        if not isinstance(item,dict) or item.get("role") not in ("point_in_time_listings","historical_orderbook"):
            raise ValueError("invalid_historical_artifact_role")
        relative=item.get("path")
        digest=item.get("sha256")
        if not isinstance(relative,str) or not relative or not isinstance(digest,str) or len(digest)!=64:
            raise ValueError("invalid_historical_artifact_reference")
        try:
            int(digest,16)
        except ValueError as exc:
            raise ValueError("invalid_historical_artifact_reference") from exc
        if Path(relative).is_absolute() or not Path(relative).parts or Path(relative).parts[0] in (".", "..") or ".." in Path(relative).parts:
            raise ValueError("historical_artifact_missing_or_unsafe")
        unresolved=root/relative
        if any(part.is_symlink() for part in (unresolved, *unresolved.parents) if part!=root and part.is_relative_to(root)):
            raise ValueError("historical_artifact_missing_or_unsafe")
        target=unresolved.resolve()
        if target in seen_paths:
            raise ValueError("duplicate_historical_artifact_path")
        seen_paths.add(target)
        if not target.is_relative_to(root) or not target.is_file():
            raise ValueError("historical_artifact_missing_or_unsafe")
        if target.stat().st_size == 0:
            raise ValueError("empty_historical_artifact")
        hasher=hashlib.sha256()
        with target.open('rb') as source:
            for chunk in iter(lambda: source.read(1024*1024), b''):
                hasher.update(chunk)
        actual=hasher.hexdigest()
        if actual!=digest.lower():
            raise ValueError("historical_artifact_checksum_mismatch")
        verified_roles.add(item["role"])
    if verified_roles!={"point_in_time_listings","historical_orderbook"}:
        raise ValueError("incomplete_historical_artifact_roles")
    # Checksums prove byte integrity only, not provider authenticity or complete market coverage.
    return {"decision_ms":decision_ms,"historical_evidence_verified":True,\n            "provider_authenticity_verified":False,"historical_market_coverage_verified":False,
            "source_type":manifest["source_type"],"artifact_count":len(artifacts)}
