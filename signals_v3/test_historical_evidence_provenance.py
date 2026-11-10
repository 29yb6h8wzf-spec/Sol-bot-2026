import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from signals_v3.historical_evidence_provenance import verify_historical_evidence_manifest

class HistoricalEvidenceProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.manifest={"current_only":False,"historical_universe_verified":True,
                       "source_type":"archived_orderbook_snapshots",
                       "coverage_start_ms":1000,"coverage_end_ms":2000,
                       "source_reference":"archive-sha256:example",
                       "point_in_time_listings_verified":True,
                       "spread_and_depth_verified":True,
                       "evidence_artifacts":[]}
    def check(self,manifest,decision=1500):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"manifest.json"
            manifest=dict(manifest)
            if not manifest["evidence_artifacts"]:
                artifacts=[]
                for role in ("point_in_time_listings","historical_orderbook"):
                    filename=role+".csv"
                    payload=(role+"\\n").encode()
                    (Path(directory)/filename).write_bytes(payload)
                    artifacts.append({"role":role,"path":filename,"sha256":hashlib.sha256(payload).hexdigest()})
                manifest["evidence_artifacts"]=artifacts
            p.write_text(json.dumps(manifest))
            return verify_historical_evidence_manifest(p,decision)
    def test_valid_declared_manifest(self):
        self.assertTrue(self.check(self.manifest)["historical_evidence_verified"])
    def test_missing_artifact_rejected(self):
        self.manifest["evidence_artifacts"]=[{"role":"historical_orderbook","path":"missing.csv","sha256":"0"*64}]
        with self.assertRaisesRegex(ValueError,"historical_artifact_missing_or_unsafe"):
            self.check(self.manifest)
    def test_symlink_artifact_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            payload=b"archived-book"
            (root/"real.csv").write_bytes(payload)
            (root/"alias.csv").symlink_to(root/"real.csv")
            manifest=dict(self.manifest)
            manifest["evidence_artifacts"]=[{"role":"historical_orderbook","path":"alias.csv","sha256":hashlib.sha256(payload).hexdigest()}]
            p=root/"manifest.json"
            p.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,"historical_artifact_missing_or_unsafe"):
                verify_historical_evidence_manifest(p,1500)
    def test_absolute_artifact_path_rejected(self):
        self.manifest["evidence_artifacts"]=[{"role":"historical_orderbook","path":"/tmp/other.csv","sha256":"0"*64}]
        with self.assertRaisesRegex(ValueError,"historical_artifact_missing_or_unsafe"):
            self.check(self.manifest)
    def test_parent_traversal_rejected(self):
        self.manifest["evidence_artifacts"]=[{"role":"historical_orderbook","path":"../other.csv","sha256":"0"*64}]
        with self.assertRaisesRegex(ValueError,"historical_artifact_missing_or_unsafe"):
            self.check(self.manifest)
    def test_current_capture_rejected(self):
        self.manifest["current_only"]=True
        self.manifest["historical_universe_verified"]=False
        with self.assertRaisesRegex(ValueError,"unverified_historical_universe_provenance"):
            self.check(self.manifest)
    def test_outside_coverage_rejected(self):
        with self.assertRaisesRegex(ValueError,"historical_evidence_outside_coverage"):
            self.check(self.manifest,3000)
    def test_missing_depth_evidence_rejected(self):
        self.manifest["spread_and_depth_verified"]=False
        with self.assertRaisesRegex(ValueError,"incomplete_historical_evidence"):
            self.check(self.manifest)

if __name__=="__main__":
    unittest.main()
