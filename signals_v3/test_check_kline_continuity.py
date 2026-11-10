import tempfile,unittest,zipfile
from pathlib import Path
from signals_v3.check_kline_continuity import check_kline_continuity

class KlineContinuityTests(unittest.TestCase):
    def test_missing_bars_detected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"sample.zip"
            with zipfile.ZipFile(p,"w") as z:
                z.writestr("bars.csv","1788220800000,1,2\n1788220920000,1,2\n")
            r=check_kline_continuity(p,"1m","2026-09")
            self.assertEqual(r["missing_intervals"],1)
            self.assertFalse(r["continuous"])
    def test_duplicate_bars_detected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"sample.zip"
            with zipfile.ZipFile(p,"w") as z:
                z.writestr("bars.csv","1788220800000,1,2\n1788220800000,1,2\n")
            r=check_kline_continuity(p,"1m","2026-09")
            self.assertEqual(r["non_increasing"],1)
            self.assertFalse(r["continuous"])
    def test_reject_funding(self):
        with self.assertRaisesRegex(ValueError,"kline_interval_required"):
            check_kline_continuity("unused","fundingRate","2026-09")
if __name__=="__main__":unittest.main()
