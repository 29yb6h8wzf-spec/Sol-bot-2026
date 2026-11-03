"""Offline tests for demo risk adapter."""
import unittest
from demo_risk_adapter import preflight, load_account

def account():
    return {"equity":"150","day_start":"150","used_margin":"0","open_risk":"0","leverage":2}

def intent():
    return {"symbol":"XRP/USDT:USDT","side":"long",
            "source":"verified_85_score_engine","score":90,
            "entry":"2","stop":"1.9","target":"2.2","quantity":"10"}

class RiskTests(unittest.TestCase):
    def test_missing_plan(self):
        x=intent()
        del x["stop"]
        self.assertEqual(preflight(x,account())[1],"independent_order_plan_missing")

    def test_valid_offline(self):
        self.assertEqual(preflight(intent(),account()),(True,"approved_offline_only"))

    def test_per_trade_limit(self):
        x=intent()
        x["quantity"]="20"
        self.assertEqual(preflight(x,account())[1],"per_trade_risk")

    def test_daily_loss(self):
        a=account()
        a["equity"]="142.50"
        self.assertEqual(preflight(intent(),a)[1],"daily_loss_limit")

    def test_leverage(self):
        a=account()
        a["leverage"]=3
        self.assertEqual(preflight(intent(),a)[1],"invalid_account")

    def test_no_snapshot(self):
        self.assertIsNone(load_account("/tmp/nonexistent-demo-risk-snapshot-3284"))

if __name__=="__main__":
    unittest.main()
