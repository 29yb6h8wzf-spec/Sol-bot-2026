"""Offline contract tests for provenance-gated replay."""
import unittest
from signals_v3.historical_universe_replay import replay_verified_historical_universe

class VerifiedReplayTests(unittest.TestCase):
    def test_requires_manifest(self):
        with self.assertRaisesRegex(ValueError, "missing_historical_evidence_manifest"):
            replay_verified_historical_universe([], [1000], None)

    def test_rejects_current_only_manifest_before_replay(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"manifest.json"
            path.write_text(json.dumps({"current_only":True,"historical_universe_verified":False}))
            with self.assertRaisesRegex(ValueError, "unverified_historical_universe_provenance"):
                replay_verified_historical_universe([], [1000], path)

    def test_requires_explicit_schedule(self):
        with self.assertRaisesRegex(ValueError, "missing_expected_decision_schedule"):
            replay_verified_historical_universe([], None, "manifest.json")

if __name__=="__main__":
    unittest.main()
