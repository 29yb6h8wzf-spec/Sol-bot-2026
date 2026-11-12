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
    def test_checksum_only_manifest_verifies_artifact_integrity(self):
        result = self.check(self.manifest)
        self.assertTrue(result["artifact_integrity_verified"])
        self.assertIs(result["historical_evidence_verified"], False)
    def test_checksum_does_not_certify_provider_or_market_coverage(self):
        result=self.check(self.manifest)
        self.assertFalse(result["provider_authenticity_verified"])
        self.assertFalse(result["historical_market_coverage_verified"])
    def test_whitespace_source_reference_rejected(self):
        self.manifest["source_reference"]="  "
        with self.assertRaisesRegex(ValueError,"missing_historical_evidence_source_reference"):
            self.check(self.manifest)
    def test_negative_coverage_rejected(self):
        self.manifest["coverage_start_ms"]=-1
        with self.assertRaisesRegex(ValueError,"historical_evidence_outside_coverage"):
            self.check(self.manifest)
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
    def test_empty_artifact_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/"empty.csv").write_bytes(b"")
            m=dict(self.manifest)
            m["evidence_artifacts"]=[{"role":"historical_orderbook","path":"empty.csv","sha256":hashlib.sha256(b"").hexdigest()}]
            p=root/"manifest.json"
            p.write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError,"empty_historical_artifact"):
                verify_historical_evidence_manifest(p,1500)
    def test_duplicate_artifact_path_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            payload=b"placeholder"
            (root/"same.csv").write_bytes(payload)
            m=dict(self.manifest)
            m["evidence_artifacts"]=[{"role":role,"path":"same.csv","sha256":hashlib.sha256(payload).hexdigest()}
                                     for role in ("point_in_time_listings","historical_orderbook")]
            p=root/"manifest.json"
            p.write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError,"duplicate_historical_artifact_path"):
                verify_historical_evidence_manifest(p,1500)
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
