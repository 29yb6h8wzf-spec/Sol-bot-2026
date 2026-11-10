import unittest
from signals_v3.archive_coverage_report import summarize

class CoverageReportTests(unittest.TestCase):
    def test_coverage_and_reasons(self):
        report=summarize({"records":[
            {"symbol":"ADAUSDT","month":"2026-09","verified":True},
            {"symbol":"ADAUSDT","month":"2026-09","verified":False,"reason":"archive_missing"},
            {"symbol":"SOLUSDT","month":"2026-09","verified":False,"reason":"zip_corrupt"}]})
        self.assertEqual((report["total"],report["verified"],report["blocked"]),(3,1,2))
        self.assertEqual(report["coverage_percent"],33.33)
        self.assertEqual(report["blockers"],{"archive_missing":1,"zip_corrupt":1})
        self.assertEqual(report["by_symbol"]["ADAUSDT"],{"verified":1,"blocked":1})
        self.assertFalse(report["dynamic_backtest_ready"])
    def test_empty_audit_not_ready(self):
        report=summarize({"records":[]})
        self.assertEqual(report["coverage_percent"],0)
        self.assertFalse(report["dynamic_backtest_ready"])
    def test_invalid_audit(self):
        with self.assertRaisesRegex(ValueError,"missing_audit_records"):
            summarize({})
if __name__=="__main__":unittest.main()
