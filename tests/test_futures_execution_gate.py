"""Offline regression tests for the futures execution boundary."""
import unittest

from futures_engine.execution_gate import ExecutionGate, LiveTradingDisabled, OrderIntent


class ExecutionGateTests(unittest.TestCase):
    def test_live_mode_never_unlocks(self):
        for mode in ('live', 'LIVE', 'testnet', '', None):
            with self.subTest(mode=mode), self.assertRaises(LiveTradingDisabled):
                ExecutionGate(mode)

    def test_order_methods_always_block(self):
        gate = ExecutionGate()
        for name in ('submit_order', 'cancel_order', 'set_leverage'):
            with self.subTest(method=name), self.assertRaises(LiveTradingDisabled):
                getattr(gate, name)(symbol='BTC/USDT:USDT', amount=1)

    def test_paper_intent_is_not_submitted(self):
        result = ExecutionGate().simulate(OrderIntent('BTC/USDT:USDT', 'buy', '0.001'))
        self.assertEqual(result['status'], 'not_submitted')
        self.assertEqual(result['mode'], 'paper')

    def test_rejects_invalid_intents(self):
        for intent in (
            OrderIntent('BTC/USDT', 'buy', '1'),
            OrderIntent('BTC/USDT:USDT', 'long', '1'),
            OrderIntent('BTC/USDT:USDT', 'buy', '-1'),
            OrderIntent('BTC/USDT:USDT', 'buy', 'NaN'),
            OrderIntent('BTC/USDT:USDT', 'buy', 'Infinity'),
            OrderIntent('BTC/USDT:USDT', 'buy', '0'),
            OrderIntent('BTC/USDT:USDT', 'buy', '1', reduce_only='false'),
        ):
            with self.subTest(intent=intent), self.assertRaises(ValueError):
                ExecutionGate().simulate(intent)


if __name__ == '__main__':
    unittest.main()
