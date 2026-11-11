"""Offline adversarial checks for historical provenance; never touches an exchange."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from signals_v3.historical_evidence_provenance import verify_historical_evidence_manifest


class HistoricalProvenanceReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.listings = self.root / "listings.json"
        self.book = self.root / "orderbook.json"
        self.listings.write_bytes(b'{"symbols":["SOLUSDT"]}')
        self.book.write_bytes(b'{"bids":[],"asks":[]}')
        self.manifest = {
            "current_only": False,
            "historical_universe_verified": True,
            "source_type": "archived_orderbook_snapshots",
            "coverage_start_ms": 100,
            "coverage_end_ms": 200,
            "source_reference": "synthetic-fixture-not-provider-evidence",
            "point_in_time_listings_verified": True,
            "spread_and_depth_verified": True,
            "evidence_artifacts": [
                {"role": "point_in_time_listings", "path": "listings.json",
                 "sha256": hashlib.sha256(self.listings.read_bytes()).hexdigest()},
                {"role": "historical_orderbook", "path": "orderbook.json",
                 "sha256": hashlib.sha256(self.book.read_bytes()).hexdigest()},
            ],
        }
        self.path = self.root / "manifest.json"
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_integrity_does_not_certify_historical_data(self):
        result = verify_historical_evidence_manifest(self.path, 150)
        self.assertTrue(result["artifact_integrity_verified"])
        for key in ("historical_evidence_verified", "provider_authenticity_verified",
                    "historical_market_coverage_verified", "funding_history_verified",
                    "orderbook_history_verified", "point_in_time_universe_verified"):
            self.assertFalse(result[key])

    def test_modified_artifact_is_rejected(self):
        self.book.write_bytes(self.book.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "historical_artifact_checksum_mismatch"):
            verify_historical_evidence_manifest(self.path, 150)

    def test_duplicate_path_cannot_prove_two_roles(self):
        self.manifest["evidence_artifacts"][1]["path"] = "listings.json"
        self.manifest["evidence_artifacts"][1]["sha256"] = hashlib.sha256(
            self.listings.read_bytes()).hexdigest()
        self.save()
        with self.assertRaisesRegex(ValueError, "duplicate_historical_artifact_path"):
            verify_historical_evidence_manifest(self.path, 150)

    def test_replay_cannot_use_future_evidence(self):
        for decision in (99, 201, -1, True, 150.0):
            with self.subTest(decision=decision):
                with self.assertRaises(ValueError):
                    verify_historical_evidence_manifest(self.path, decision)

    def test_traversal_rejected_even_if_file_exists(self):
        self.manifest["evidence_artifacts"][1]["path"] = "../orderbook.json"
        self.save()
        with self.assertRaisesRegex(ValueError, "historical_artifact_missing_or_unsafe"):
            verify_historical_evidence_manifest(self.path, 150)


if __name__ == "__main__":
    unittest.main()
