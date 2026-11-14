"""Regression: byte integrity must never be reported as historical provenance."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from signals_v3.historical_evidence_provenance import verify_historical_evidence_manifest


class HistoricalEvidenceNoFalsePositiveTests(unittest.TestCase):
    def _fixture(self, root):
        artifacts = []
        for role in ("point_in_time_listings", "historical_orderbook"):
            name = role + ".json"
            payload = b'{"synthetic":true}\n'
            (root / name).write_bytes(payload)
            artifacts.append({"role": role, "path": name, "sha256": hashlib.sha256(payload).hexdigest()})
        manifest = {
            "current_only": False,
            "historical_universe_verified": True,
            "source_type": "archived_orderbook_snapshots",
            "coverage_start_ms": 1000,
            "coverage_end_ms": 2000,
            "source_reference": "synthetic-fixture-not-a-provider",
            "point_in_time_listings_verified": True,
            "spread_and_depth_verified": True,
            "evidence_artifacts": artifacts,
        }
        path = root / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def test_valid_checksums_never_prove_authentic_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._fixture(Path(directory))
            result = verify_historical_evidence_manifest(path, 1500)
            self.assertIs(result["artifact_integrity_verified"], True)
            for field in (
                "historical_evidence_verified",
                "provider_authenticity_verified",
                "historical_market_coverage_verified",
                "funding_history_verified",
                "orderbook_history_verified",
                "point_in_time_universe_verified",
            ):
                with self.subTest(field=field):
                    self.assertIs(result[field], False)

    def test_tampered_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._fixture(root)
            (root / "historical_orderbook.json").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "historical_artifact_checksum_mismatch"):
                verify_historical_evidence_manifest(path, 1500)

    def test_path_traversal_is_rejected_even_with_matching_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._fixture(root)
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["evidence_artifacts"][0]["path"] = "../outside.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "historical_artifact_missing_or_unsafe"):
                verify_historical_evidence_manifest(path, 1500)

    def test_duplicate_artifact_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._fixture(root)
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["evidence_artifacts"].append(dict(manifest["evidence_artifacts"][0]))
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate_historical_artifact_path"):
                verify_historical_evidence_manifest(path, 1500)

    def test_invalid_checksum_format_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._fixture(root)
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["evidence_artifacts"][0]["sha256"] = "g" * 64
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid_historical_artifact_reference"):
                verify_historical_evidence_manifest(path, 1500)

    def test_out_of_coverage_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._fixture(Path(directory))
            with self.assertRaisesRegex(ValueError, "historical_evidence_outside_coverage"):
                verify_historical_evidence_manifest(path, 2001)


if __name__ == "__main__":
    unittest.main()
