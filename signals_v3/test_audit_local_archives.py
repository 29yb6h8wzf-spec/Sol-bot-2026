import tempfile,unittest,zipfile
from pathlib import Path
from signals_v3.archive_acquisition_plan import build_plan
from signals_v3.audit_local_archives import audit_plan

class AuditLocalArchivesTests(unittest.TestCase):
    def test_missing_all_remains_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            result=audit_plan(build_plan(["ADAUSDT"],"2026-09","2026-09"),d)
            self.assertEqual((result["total"],result["verified"],result["blocked"]),(3,0,3))
            self.assertFalse(result["ready_for_historical_dynamic_replay"])
    def test_one_verified_archive_two_missing(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);folder=root/"ADAUSDT"/"1m";folder.mkdir(parents=True)
            with zipfile.ZipFile(folder/"ADAUSDT-1m-2026-09.zip","w") as z:
                z.writestr("data.csv","1788220800000,1,2\n1788220860000,2,3\n")
            result=audit_plan(build_plan(["ADAUSDT"],"2026-09","2026-09"),root)
            self.assertEqual((result["verified"],result["blocked"]),(1,2))
            self.assertFalse(result["historical_universe_verified"])
    def test_bad_zip_remains_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/"ADAUSDT"/"1m";folder.mkdir(parents=True)
            (folder/"ADAUSDT-1m-2026-09.zip").write_bytes(b"not a zip")
            result=audit_plan(build_plan(["ADAUSDT"],"2026-09","2026-09"),d)
            self.assertEqual(result["verified"],0)
if __name__=="__main__":unittest.main()
