"""Read-only integrity boundary tests; no network, credentials or trading."""
import hashlib
import json

import pytest

from signals_v3.historical_evidence_provenance import verify_historical_evidence_manifest


def _manifest(tmp_path):
    listings = tmp_path / "listings.json"
    book = tmp_path / "orderbook.json"
    listings.write_bytes(b'{"symbols":["SOLUSDT"]}')
    book.write_bytes(b'{"bids":[],"asks":[]}')
    manifest = {
        "current_only": False,
        "historical_universe_verified": True,
        "source_type": "archived_orderbook_snapshots",
        "coverage_start_ms": 100,
        "coverage_end_ms": 200,
        "source_reference": "offline-test-fixture",
        "point_in_time_listings_verified": True,
        "spread_and_depth_verified": True,
        "evidence_artifacts": [
            {"role": "point_in_time_listings", "path": listings.name,
             "sha256": hashlib.sha256(listings.read_bytes()).hexdigest()},
            {"role": "historical_orderbook", "path": book.name,
             "sha256": hashlib.sha256(book.read_bytes()).hexdigest()},
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path, manifest, listings, book


def test_integrity_never_certifies_provider_or_historical_completeness(tmp_path):
    path, _, _, _ = _manifest(tmp_path)
    result = verify_historical_evidence_manifest(path, 150)
    assert result["artifact_integrity_verified"] is True
    for key in ("historical_evidence_verified", "provider_authenticity_verified",
                "historical_market_coverage_verified", "funding_history_verified",
                "orderbook_history_verified", "point_in_time_universe_verified"):
        assert result[key] is False


def test_tampering_detected(tmp_path):
    path, _, _, book = _manifest(tmp_path)
    book.write_bytes(book.read_bytes() + b" ")
    with pytest.raises(ValueError, match="historical_artifact_checksum_mismatch"):
        verify_historical_evidence_manifest(path, 150)


@pytest.mark.parametrize("decision", [99, 201, -1, True, 150.0])
def test_invalid_or_out_of_coverage_decision_fails_closed(tmp_path, decision):
    path, _, _, _ = _manifest(tmp_path)
    with pytest.raises(ValueError):
        verify_historical_evidence_manifest(path, decision)


def test_duplicate_artifact_cannot_satisfy_both_roles(tmp_path):
    path, manifest, listings, _ = _manifest(tmp_path)
    manifest["evidence_artifacts"][1] = {
        "role": "historical_orderbook",
        "path": listings.name,
        "sha256": hashlib.sha256(listings.read_bytes()).hexdigest(),
    }
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate_historical_artifact_path"):
        verify_historical_evidence_manifest(path, 150)


def test_symlink_to_outside_is_rejected_even_with_matching_hash(tmp_path):
    path, manifest, _, _ = _manifest(tmp_path)
    outside = tmp_path.parent / (tmp_path.name + "-external-evidence")
    outside.write_bytes(b"external")
    link = tmp_path / "linked.json"
    link.symlink_to(outside)
    manifest["evidence_artifacts"][1] = {
        "role": "historical_orderbook", "path": link.name,
        "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
    }
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="historical_artifact_missing_or_unsafe"):
        verify_historical_evidence_manifest(path, 150)
