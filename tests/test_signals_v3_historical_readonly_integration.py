"""Read-only integration contract: checksum integrity is not historical data provenance."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from signals_v3.historical_evidence_provenance import verify_historical_evidence_manifest


class HistoricalEvidenceIntegrationTests(unittest.TestCase):
    def test_local_bytes_never_certify_provider_or_market_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = []
            for role, name in (("point_in_time_listings", "listings.csv"),
                               ("historical_orderbook", "depth.csv")):
                data = b"timestamp,symbol,value\n1000,SOLUSDT,1\n"
                (root / name).write_bytes(data)
                artifacts.append({"role": role, "path": name,
                                  "sha256": hashlib.sha256(data).hexdigest()})
            manifest = {
                "current_only": False,
                "historical_universe_verified": True,
                "source_type": "archived_orderbook_snapshots",
                "source_reference": "local-test-fixture-not-a-provider",
                "coverage_start_ms": 1000,
                "coverage_end_ms": 2000,
                "point_in_time_listings_verified": True,
                "spread_and_depth_verified": True,
                "evidence_artifacts": artifacts,
            }
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            result = verify_historical_evidence_manifest(path, 1500)
            self.assertTrue(result["historical_evidence_verified"])
            self.assertFalse(result["provider_authenticity_verified"])
            self.assertFalse(result["historical_market_coverage_verified"])
            with self.assertRaises(ValueError):
                verify_historical_evidence_manifest(path, 2001)

    def test_missing_real_artifacts_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps({
                "current_only": False, "historical_universe_verified": True,
                "source_type": "historical_market_data_provider",
                "source_reference": "unverified-provider",
                "coverage_start_ms": 0, "coverage_end_ms": 100,
                "point_in_time_listings_verified": True,
                "spread_and_depth_verified": True,
                "evidence_artifacts": [],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing_verifiable_historical_artifacts"):
                verify_historical_evidence_manifest(path, 50)


if __name__ == "__main__":
    unittest.main()
