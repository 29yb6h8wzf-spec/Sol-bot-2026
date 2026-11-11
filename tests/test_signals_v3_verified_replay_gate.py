"""Offline regression: integrity-only manifests must not authorize verified replay."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from signals_v3.historical_universe_replay import replay_verified_historical_universe


class HistoricalReplayVerificationGateTests(unittest.TestCase):
    def test_invalid_schedule_fails_before_manifest_io(self):
        # A nonexistent manifest must not mask an invalid schedule.
        # This also prevents repeated hash scans on malformed requests.
        bad_schedules = ((), (-1,), (True,), (1, 1), (2, 1), (1, 1.5), (1, "2"))
        for schedule in bad_schedules:
            with self.subTest(schedule=schedule):
                with self.assertRaisesRegex(ValueError, "invalid_expected_decision_schedule"):
                    replay_verified_historical_universe((), schedule, "/nonexistent/manifest.json")

    def test_integrity_only_manifest_fails_before_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            artifacts = []
            for role, filename in (
                ("point_in_time_listings", "listings.csv"),
                ("historical_orderbook", "book.csv"),
            ):
                data = b"timestamp,symbol,value\n1000,SOLUSDT,1\n"
                (root / filename).write_bytes(data)
                artifacts.append({
                    "role": role,
                    "path": filename,
                    "sha256": hashlib.sha256(data).hexdigest(),
                })
            manifest = {
                "current_only": False,
                "historical_universe_verified": True,
                "source_type": "archived_orderbook_snapshots",
                "source_reference": "synthetic-test-fixture",
                "coverage_start_ms": 1000,
                "coverage_end_ms": 2000,
                "point_in_time_listings_verified": True,
                "spread_and_depth_verified": True,
                "evidence_artifacts": artifacts,
            }
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            # The empty observations are deliberate: provenance must reject
            # first, rather than allow the replay to treat checksums as proof.
            with self.assertRaisesRegex(ValueError, "unverified_historical_evidence"):
                replay_verified_historical_universe(
                    [{"decision_ms": 1500, "observations": (),
                      "expected_symbols": ("SOLUSDT",)}],
                    (1500,), path,
                )


if __name__ == "__main__":
    unittest.main()
