import os
import unittest
from unittest.mock import Mock, patch
from decimal import Decimal
from futures_engine.breakout_execution import route_breakout
from futures_engine.live import LiveSafetyError

class RouteTest(unittest.TestCase):
    def setUp(self):
        self.now = 1794676800000
        self.exchange = Mock()
        e = self.exchange
        pair = "SOL/USDT:USDT"
        e.fetch_order_book.return_value = {"asks": [[100, 1]]}
        e.amount_to_precision.side_effect = lambda s,q: str(Decimal(q).quantize(Decimal(".001"), rounding="ROUND_DOWN"))
        e.market.return_value = {"linear": True, "swap": True, "active": True, "limits": {}}
        e.market_id.return_value = "SOLUSDT"
        e.fetch_positions.side_effect = [[], [{"contracts": ".393", "symbol": pair}]]
        e.fetch_open_orders.return_value = []
        e.fetch_position_mode.return_value = {"hedged": False}
        e.fapiPrivatePostAlgoOrder.side_effect = [{"algoId": 1}, {"algoId": 2}]
        e.fapiPrivateGetOpenAlgoOrders.side_effect = [[], [{"algoId":1}, {"algoId":2}]]
        self.journal = Mock()
        self.account = {"equity": 150, "day_start_equity": 150}

    def invoke(self, observation, age=0):
        with patch("futures_engine.breakout_execution.time.time_ns",return_value=(self.now+age)*1_000_000), \
             patch("futures_engine.breakout_execution.scan",return_value=observation), \
             patch.dict(os.environ, {"TRADING_MODE":"live","SIGNALPILOT_LIVE_ARMED":"YES_I_ACCEPT_REAL_LOSSES",
                                     "BINANCE_BRACKET_CERTIFIED":"YES_TESTNET_VERIFIED"}):
            return route_breakout(self.exchange, "SOLUSDT", self.now, journal=self.journal, account=self.account)

    def test_candidate_reaches_protected_engine(self):
        result = self.invoke({"status":"research_candidate","direction":"LONG","entry_reference":100,
                              "stop_reference":99,"target_reference":102})
        self.assertEqual(result["stop"]["algoId"], 1)
        self.assertEqual(result["target"]["algoId"], 2)
        self.exchange.create_order.assert_called_once()
        self.journal.mark.assert_called_with("vb-SOLUSDT-1794676800000", "PROTECTED")

    def test_no_signal(self):
        self.assertEqual(self.invoke({"status":"no_candidate"}), {"status":"no_candidate"})
        self.exchange.create_order.assert_not_called()

    def test_expired_signal(self):
        with self.assertRaisesRegex(LiveSafetyError,"expired"):
            self.invoke({}, 60_000)
        self.exchange.create_order.assert_not_called()
