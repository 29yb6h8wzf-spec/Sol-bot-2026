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

    def test_checksum_only_artifacts_cannot_authorize_replay(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        from signals_v3.dynamic_universe import UniverseObservation
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            artifacts=[]
            for role in ("point_in_time_listings","historical_orderbook"):
                payload=(role+"\\n").encode()
                filename=role+".csv"
                (root/filename).write_bytes(payload)
                artifacts.append({"role":role,"path":filename,"sha256":hashlib.sha256(payload).hexdigest()})
            manifest={"current_only":False,"historical_universe_verified":True,
                      "source_type":"archived_orderbook_snapshots","coverage_start_ms":1000,
                      "coverage_end_ms":2000,"source_reference":"fixture-only",
                      "point_in_time_listings_verified":True,"spread_and_depth_verified":True,
                      "evidence_artifacts":artifacts}
            path=root/"manifest.json"
            path.write_text(json.dumps(manifest))
            obs=UniverseObservation(symbol="SOLUSDT",observed_at_ms=1500,
                last_price_usd=100.0,quote_volume_24h_usd=20_000_000.0,
                spread_bps=2.0,bid_depth_10bps_usd=20_000.0,
                ask_depth_10bps_usd=20_000.0,min_notional_usd=5.0,
                status="TRADING",contract_type="PERPETUAL",quote_asset="USDT")
            decisions=[{"decision_ms":1500,"expected_symbols":["SOLUSDT"],"observations":[obs]}]
            with self.assertRaisesRegex(ValueError,"unverified_historical_evidence"):
                replay_verified_historical_universe(decisions,[1500],path)
            (root/"historical_orderbook.csv").write_bytes(b"tampered after signing")
            with self.assertRaisesRegex(ValueError,"historical_artifact_checksum_mismatch"):
                replay_verified_historical_universe(decisions,[1500],path)
            with self.assertRaisesRegex(ValueError,"historical_evidence_outside_coverage"):
                replay_verified_historical_universe(decisions,[2500],path)

    def test_lazy_decision_feed_rejected_before_manifest_io(self):
        class ExplodingFeed:
            def __iter__(self):
                raise AssertionError("lazy feed must not be consumed")

        for feed in (ExplodingFeed(), iter(()), (x for x in ())):
            with self.subTest(feed=type(feed).__name__):
                with self.assertRaisesRegex(ValueError, "invalid_historical_decision_container"):
                    replay_verified_historical_universe(feed, [1000], "/nonexistent/manifest.json")

    def test_materialized_decisions_still_reach_provenance_gate(self):
        for feed in ([], ()):
            with self.subTest(feed=type(feed).__name__):
                with self.assertRaises(FileNotFoundError):
                    replay_verified_historical_universe(feed, [1000], "/nonexistent/manifest.json")

    def test_requires_explicit_schedule(self):
        with self.assertRaisesRegex(ValueError, "missing_expected_decision_schedule"):
            replay_verified_historical_universe([], None, "manifest.json")

if __name__=="__main__":
    unittest.main()
