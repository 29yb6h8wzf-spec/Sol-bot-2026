import unittest
from dataclasses import replace
from signals_v3.spec import SPEC

class V3SpecTests(unittest.TestCase):
    def test_default_research_only(self):
        SPEC.validate()
        self.assertFalse(SPEC.execution_authorized)
        self.assertEqual(SPEC.train_months + SPEC.locked_oos_months,24)
    def test_reject_user_requested_5x(self):
        with self.assertRaisesRegex(ValueError,"risk_limits_exceeded"):
            replace(SPEC,max_leverage=5).validate()
    def test_reject_user_requested_2_percent_risk(self):
        with self.assertRaisesRegex(ValueError,"risk_limits_exceeded"):
            replace(SPEC,max_risk_fraction_of_market_allocation=.02).validate()
    def test_reject_user_requested_8_percent_daily(self):
        with self.assertRaisesRegex(ValueError,"portfolio_limits_exceeded"):
            replace(SPEC,max_daily_loss_fraction=.08).validate()
    def test_never_authorize_execution(self):
        with self.assertRaisesRegex(ValueError,"research_only_required"):
            replace(SPEC,execution_authorized=True).validate()
    def test_split_must_balance(self):
        with self.assertRaisesRegex(ValueError,"invalid_chronological_split"):
            replace(SPEC,locked_oos_months=5).validate()
if __name__=="__main__":unittest.main()
