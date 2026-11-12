import tempfile,unittest,zipfile
from pathlib import Path
from signals_v3.verify_archive import verify_archive

class VerifyArchiveTests(unittest.TestCase):
    def make_zip(self,root,rows):
        path=Path(root)/"ADAUSDT-1m-2026-09.zip"
        with zipfile.ZipFile(path,"w") as z:z.writestr("data.csv",rows)
        return path
    def test_valid_archive(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.make_zip(d,"1780272000000,1,2\n1780272060000,2,3\n")
            # 2026-06 timestamps must not be accepted as September data.
            with self.assertRaisesRegex(ValueError,"timestamp_outside_month"):
                verify_archive(p,"1m","2026-09")
    def test_valid_month(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.make_zip(d,"1788220800000,1,2\n1788220860000,2,3\n")
            r=verify_archive(p,"1m","2026-09")
            self.assertEqual(r["rows"],2)
            self.assertEqual(len(r["sha256"]),64)
            self.assertFalse(r["historical_universe_verified"])
    def test_duplicate_timestamp_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.make_zip(d,"1788220800000,1,2\n1788220800000,2,3\n")
            with self.assertRaisesRegex(ValueError,"non_monotonic_timestamps"):
                verify_archive(p,"1m","2026-09")
    def test_missing_archive_rejected(self):
        with self.assertRaisesRegex(ValueError,"archive_missing"):
            verify_archive("/no/such/archive.zip","1m","2026-09")
if __name__=="__main__":unittest.main()
