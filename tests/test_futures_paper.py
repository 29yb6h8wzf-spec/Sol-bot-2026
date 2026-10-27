import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from futures_engine.core import Config, plan_trade, crossover_signal
from futures_engine.paper import PaperLedger


class RiskTests(unittest.TestCase):
    def test_risk_is_capped_including_costs(self):
        plan = plan_trade(Config(), 'long', 100, 1000, 1000)
        self.assertLessEqual(D(plan['max_estimated_loss']), D('10'))
        self.assertEqual(D(plan['stop']), D('98'))
        self.assertEqual(D(plan['target']), D('104'))

    def test_short_and_daily_drawdown(self):
        plan = plan_trade(Config(), 'short', 100, 1000, 1000)
        self.assertEqual(D(plan['stop']), D('102'))
        self.assertEqual(D(plan['target']), D('96'))
        with self.assertRaisesRegex(ValueError, 'drawdown'):
            plan_trade(Config(), 'long', 100, 949, 1000)

    def test_rejects_dust_and_unsafe_config(self):
        with self.assertRaisesRegex(ValueError, 'dust'):
            plan_trade(Config(), 'long', 100, 1000, 1000, minimum_amount=1000)
        with self.assertRaisesRegex(ValueError, 'risk'):
            Config(risk_fraction=D('0.02')).validate()
        with self.assertRaisesRegex(ValueError, 'leverage'):
            Config(leverage=10).validate()

    def test_no_cross_on_constant_prices(self):
        bars = [[i*900000,100,100,100,100,10] for i in range(210)]
        self.assertIsNone(crossover_signal(bars))


class PaperTests(unittest.TestCase):
    def test_stop_wins_if_stop_and_target_hit_same_bar(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'ledger.json'
            ledger = PaperLedger(path)
            ledger.roll_day(1800000000000)
            plan = plan_trade(Config(), 'long', 100, 1000, 1000)
            ledger.open_position(plan, 1800000000000)
            result = ledger.evaluate_exit([[1800000900000,100,105,97,100,1]],D('0.0006'),D('0.0005'))
            self.assertEqual(result['reason'],'stop')
            self.assertLess(D(ledger.state['equity']),D('1000'))
            self.assertIsNone(PaperLedger(path).state['position'])
            with self.assertRaisesRegex(ValueError,'duplicate'):
                ledger.open_position(plan, 1800000000000)


if __name__ == '__main__':
    unittest.main()
