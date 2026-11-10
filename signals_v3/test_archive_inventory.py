import unittest
from signals_v3.archive_inventory import ArchiveRecord,inventory

class ArchiveInventoryTests(unittest.TestCase):
    def test_complete_files_do_not_claim_historical_universe(self):
        rows=[ArchiveRecord("ADAUSDT","2026-09",i,"archive.zip",True) for i in ("1m","5m","fundingRate")]
        r=inventory(rows,["2026-09"],["ADAUSDT"])
        self.assertTrue(r["complete_archive_coverage"])
        self.assertFalse(r["historical_universe_verified"])
        self.assertFalse(r["replay_authorized"])
    def test_missing_funding_detected(self):
        rows=[ArchiveRecord("ADAUSDT","2026-09",i,"archive.zip",True) for i in ("1m","5m")]
        r=inventory(rows,["2026-09"],["ADAUSDT"])
        self.assertEqual(r["missing"],[["ADAUSDT","2026-09","fundingRate"]])
    def test_unverified_archive_detected(self):
        rows=[ArchiveRecord("ADAUSDT","2026-09",i,"archive.zip",i!="5m") for i in ("1m","5m","fundingRate")]
        r=inventory(rows,["2026-09"],["ADAUSDT"])
        self.assertEqual(r["unverified"],[["ADAUSDT","2026-09","5m"]])
    def test_duplicate_archive_rejected(self):
        row=ArchiveRecord("ADAUSDT","2026-09","1m","a.zip",True)
        with self.assertRaisesRegex(ValueError,"duplicate_archive_record"):
            inventory([row,row],["2026-09"],["ADAUSDT"])
if __name__=="__main__":unittest.main()
