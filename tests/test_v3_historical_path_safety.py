"""Fail-closed historical provenance regression tests (offline only)."""
import hashlib
import json
import pytest

from signals_v3.historical_evidence_provenance import verify_historical_evidence_manifest


def test_ambiguous_cross_platform_artifact_paths_fail_closed(tmp_path):
    (tmp_path / "listings.json").write_text("{}", encoding="utf-8")
    (tmp_path / "orderbook.json").write_text("{}", encoding="utf-8")
    def artifact(role, name):
        return {"role": role, "path": name,
                "sha256": hashlib.sha256(b"{}").hexdigest()}
    manifest = {
        "current_only": False,
        "historical_universe_verified": True,
        "source_type": "archived_orderbook_snapshots",
        "source_reference": "offline-fixture-not-real-history",
        "coverage_start_ms": 1,
        "coverage_end_ms": 100,
        "point_in_time_listings_verified": True,
        "spread_and_depth_verified": True,
        "evidence_artifacts": [
            artifact("point_in_time_listings", "listings.json"),
            artifact("historical_orderbook", "orderbook.json"),
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    result = verify_historical_evidence_manifest(path, 50)
    assert result["artifact_integrity_verified"] is True
    assert result["historical_evidence_verified"] is False
    assert result["funding_history_verified"] is False
    assert result["orderbook_history_verified"] is False

    for unsafe in ("..\\orderbook.json", "orderbook.json\\suffix", "orderbook.json\\x00suffix"):
        manifest["evidence_artifacts"][1]["path"] = unsafe
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with pytest.raises(ValueError, match="historical_artifact_missing_or_unsafe"):
            verify_historical_evidence_manifest(path, 50)
