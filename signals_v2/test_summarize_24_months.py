import unittest
from signals_v2.summarize_24_months import summarize

class SummaryTests(unittest.TestCase):
    def test_weighted_by_trades_not_months(self):
        import tempfile,json
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            paths=[]
            for month,n,net in (("2026-01",1,2.0),("2026-02",9,-9.0)):
                path=Path(tmp)/(month+".json")
                symbol={"trades":n,"net_r_total":net,"mean_net_r":net/n}
                path.write_text(json.dumps({"month":month,"research_only":True,
                  "out_of_sample_certified":False,"symbols":{"SOLUSDT":symbol,"XRPUSDT":symbol}}))
                paths.append(path)
            out=summarize(paths)
            self.assertAlmostEqual(out["symbols"]["SOLUSDT"]["weighted_mean_net_r"],-0.7)
            self.assertFalse(out["oos_certified"])
    def test_duplicate_month_rejected(self):
        import tempfile,json
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"x.json";p.write_text(json.dumps({"month":"2026-01"}))
            with self.assertRaisesRegex(ValueError,"duplicate_month"):summarize([p,p])
if __name__=="__main__":unittest.main()
