import unittest
from signals_v3.archive_acquisition_plan import archive_url,build_plan,months_between

class ArchiveAcquisitionPlanTests(unittest.TestCase):
    def test_month_rollover(self):
        self.assertEqual(months_between("2025-12","2026-02"),("2025-12","2026-01","2026-02"))
    def test_candidate_urls(self):
        self.assertEqual(archive_url("ADAUSDT","2026-09","1m"),
            "https://data.binance.vision/data/futures/um/monthly/klines/ADAUSDT/1m/ADAUSDT-1m-2026-09.zip")
        self.assertEqual(archive_url("ADAUSDT","2026-09","fundingRate"),
            "https://data.binance.vision/data/futures/um/monthly/fundingRate/ADAUSDT/ADAUSDT-fundingRate-2026-09.zip")
    def test_plan_dedupes_and_never_claims_verified(self):
        p=build_plan(["ADAUSDT","ADAUSDT","SOLUSDT"],"2026-08","2026-09")
        self.assertEqual(len(p["records"]),12)
        self.assertFalse(p["historical_universe_verified"])
        self.assertTrue(all(not r["downloaded"] and not r["verified"] for r in p["records"]))
    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):months_between("2026-10","2026-09")
        with self.assertRaises(ValueError):archive_url("BAD/USDT","2026-09","5m")
if __name__=="__main__":unittest.main()
