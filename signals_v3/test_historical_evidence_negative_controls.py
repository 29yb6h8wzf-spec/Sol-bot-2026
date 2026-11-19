"""Historical evidence cannot be certified by self-declared manifest flags.

These are offline negative controls, not provider-authenticated fixtures.
"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from signals_v3.historical_evidence_provenance import verify_historical_evidence_manifest
from signals_v3.historical_universe_replay import replay_verified_historical_universe


class HistoricalEvidenceNegativeControls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        artifacts = []
        for role in ("point_in_time_listings", "historical_orderbook"):
            payload = (role + "\n").encode("utf-8")
            name = role + ".csv"
            (root / name).write_bytes(payload)
            artifacts.append({
                "role": role, "path": name,
                "sha256": hashlib.sha256(payload).hexdigest(),
            })
        self.manifest = {
            "current_only": False,
            "historical_universe_verified": True,
            "source_type": "historical_market_data_provider",
            "source_reference": "untrusted-test-fixture",
            "coverage_start_ms": 1000,
            "coverage_end_ms": 2000,
            "point_in_time_listings_verified": True,
            "spread_and_depth_verified": True,
            "evidence_artifacts": artifacts,
        }
        self.path = root / "manifest.json"

    def verify(self):
        self.path.write_text(json.dumps(self.manifest), encoding="utf-8")
        return verify_historical_evidence_manifest(self.path, 1500)

    def test_self_declared_verification_flags_cannot_certify_history(self):
        self.manifest.update({
            "historical_evidence_verified": True,
            "provider_authenticity_verified": True,
            "historical_market_coverage_verified": True,
            "funding_history_verified": True,
            "orderbook_history_verified": True,
            "point_in_time_universe_verified": True,
        })
        result = self.verify()
        self.assertTrue(result["artifact_integrity_verified"])
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

    def test_claimed_funding_without_funding_artifact_is_not_verified(self):
        self.manifest["funding_history_verified"] = True
        result = self.verify()
        self.assertIs(result["funding_history_verified"], False)

    def test_verified_replay_rejects_self_certified_manifest(self):
        self.manifest.update({
            "historical_evidence_verified": True,
            "provider_authenticity_verified": True,
            "historical_market_coverage_verified": True,
            "funding_history_verified": True,
            "orderbook_history_verified": True,
            "point_in_time_universe_verified": True,
        })
        self.verify()
        with self.assertRaisesRegex(ValueError, "unverified_historical_evidence"):
            replay_verified_historical_universe([], [1500], self.path)


if __name__ == "__main__":
    unittest.main()
