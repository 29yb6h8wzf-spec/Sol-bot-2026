import unittest
from signals_v3.diagnose_pilot import diagnose

class DiagnosticTests(unittest.TestCase):
    def report(self):
        return {"research_only":True,"out_of_sample_certified":False,
            "symbols":{"SOLUSDT":{"trades":3,"net_r_total":3.,
                "strategies":{"volatility_breakout":{"trades":3,"net_r_total":3.}}}}}
    def test_small_positive_sample_never_promoted(self):
        d=diagnose(self.report())
        self.assertFalse(d["promotion_allowed"])
        self.assertTrue(d["strategies"]["volatility_breakout"]["insufficient_sample"])
    def test_reject_bad_counts(self):
        r=self.report();r["symbols"]["SOLUSDT"]["trades"]=4
        with self.assertRaisesRegex(ValueError,"inconsistent_trade_totals"):diagnose(r)
    def test_reject_claimed_oos(self):
        r=self.report();r["out_of_sample_certified"]=True
        with self.assertRaisesRegex(ValueError,"untrusted_research_report"):diagnose(r)
if __name__=="__main__":unittest.main()
