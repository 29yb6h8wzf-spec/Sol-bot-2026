"""Offline adversarial tests for the historical evidence integrity boundary.

These synthetic fixtures never assert provider authenticity or market coverage.
"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from signals_v3.historical_evidence_provenance import verify_historical_evidence_manifest


class HistoricalEvidenceAdversarialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.artifacts = []
        for role, name in (("point_in_time_listings", "listings.csv"),
                           ("historical_orderbook", "depth.csv")):
            payload = b"timestamp,symbol,value\n1000,SOLUSDT,1\n"
            (self.root / name).write_bytes(payload)
            self.artifacts.append({"role": role, "path": name,
                                   "sha256": hashlib.sha256(payload).hexdigest()})
        self.manifest = {
            "current_only": False,
            "historical_universe_verified": True,
            "source_type": "archived_orderbook_snapshots",
            "source_reference": "synthetic-test-only",
            "coverage_start_ms": 1000,
            "coverage_end_ms": 2000,
            "point_in_time_listings_verified": True,
            "spread_and_depth_verified": True,
            "evidence_artifacts": self.artifacts,
        }
        self.path = self.root / "manifest.json"

    def verify(self):
        self.path.write_text(json.dumps(self.manifest), encoding="utf-8")
        return verify_historical_evidence_manifest(self.path, 1500)

    def test_valid_fixture_only_proves_integrity(self):
        result = self.verify()
        self.assertTrue(result["artifact_integrity_verified"])
        for field in ("historical_evidence_verified", "provider_authenticity_verified",
                      "historical_market_coverage_verified", "funding_history_verified",
                      "orderbook_history_verified", "point_in_time_universe_verified"):
            self.assertFalse(result[field], field)

    def test_tampered_bytes_rejected(self):
        (self.root / "depth.csv").write_bytes(b"modified")
        with self.assertRaisesRegex(ValueError, "checksum_mismatch"):
            self.verify()

    def test_duplicate_artifact_path_rejected(self):
        self.artifacts[1]["path"] = self.artifacts[0]["path"]
        with self.assertRaisesRegex(ValueError, "duplicate_historical_artifact_path"):
            self.verify()

    def test_traversal_rejected(self):
        self.artifacts[0]["path"] = "../outside.csv"
        with self.assertRaisesRegex(ValueError, "missing_or_unsafe"):
            self.verify()

    def test_symlink_rejected(self):
        (self.root / "alias.csv").symlink_to(self.root / "listings.csv")
        self.artifacts[0]["path"] = "alias.csv"
        with self.assertRaisesRegex(ValueError, "missing_or_unsafe"):
            self.verify()

    def test_missing_role_rejected(self):
        self.artifacts.pop()
        with self.assertRaisesRegex(ValueError, "incomplete_historical_artifact_roles"):
            self.verify()

    def test_boolean_decision_timestamp_rejected(self):
        self.path.write_text(json.dumps(self.manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "invalid_decision_timestamp"):
            verify_historical_evidence_manifest(self.path, True)

    def test_claimed_coverage_does_not_override_time_bounds(self):
        self.path.write_text(json.dumps(self.manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "outside_coverage"):
            verify_historical_evidence_manifest(self.path, 2001)


if __name__ == "__main__":
    unittest.main()
