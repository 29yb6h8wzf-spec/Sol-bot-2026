"""Failure-path tests for emergency flatten verification (no network/orders)."""
import os
import unittest
from decimal import Decimal
from unittest.mock import patch

from futures_engine.live import TradeIntent, LiveSafetyError, execute_protected_entry


class Journal:
    def __init__(self):
        self.states = []

    def claim(self, signal_id):
        return True

    def mark(self, signal_id, state):
        self.states.append(state)


class Exchange:
    def __init__(self, *, residual=False, stale_algo=False):
        self.residual = residual
        self.stale_algo = stale_algo
        self.position_reads = 0
        self.exit_submitted = False

    def check_required_credentials(self):
        return True

    def market_id(self, symbol):
        return "XRPUSDT"

    def market(self, symbol):
        return {"linear": True, "swap": True, "active": True,
                "limits": {"amount": {"min": 0.1}, "cost": {"min": 5}}}

    def amount_to_precision(self, symbol, amount):
        return amount

    def fetch_positions(self, symbols):
        self.position_reads += 1
        # preflight flat, then entry filled, then emergency exit reconciled
        contracts = 0 if self.position_reads == 1 else (
            4.8 if not self.exit_submitted or self.residual else 0)
        return [{"symbol": symbols[0], "contracts": contracts}]

    def fetch_open_orders(self, symbol):
        return []

    def fapiPrivateGetOpenAlgoOrders(self, params):
        if self.exit_submitted and self.stale_algo:
            return {"orders": [{"algoId": 42}]}
        return {"orders": []}

    def fetch_position_mode(self, symbol):
        return {"hedged": False}

    def set_leverage(self, leverage, symbol):
        assert leverage == 2

    def create_order(self, symbol, kind, side, amount, price, params):
        if params.get("reduceOnly"):
            self.exit_submitted = True
        return {"id": "fake"}

    def fapiPrivatePostAlgoOrder(self, params):
        raise RuntimeError("simulated protective order failure")

    def fapiPrivateDeleteAlgoOpenOrders(self, params):
        return {}

    def cancel_all_orders(self, symbol):
        return []


class EmergencyFlattenTests(unittest.TestCase):
    def intent(self):
        return TradeIntent("XRP/USDT:USDT", "long", 90,
                           "verified_85_score_engine",
                           Decimal("1.2543"), Decimal("1.2400"),
                           Decimal("1.2800"), Decimal("4.8"), "test-001")

    def run_case(self, **kwargs):
        exchange = Exchange(**kwargs)
        journal = Journal()
        with patch.dict(os.environ, {
            "TRADING_MODE": "live",
            "SIGNALPILOT_LIVE_ARMED": "YES_I_ACCEPT_REAL_LOSSES",
            "BINANCE_BRACKET_CERTIFIED": "YES_TESTNET_VERIFIED",
        }):
            with self.assertRaises(LiveSafetyError):
                execute_protected_entry(
                    exchange, self.intent(), journal=journal,
                    account={"equity": Decimal("150"),
                             "day_start_equity": Decimal("150")})
        self.assertTrue(exchange.exit_submitted)
        return journal.states

    def test_verified_flat_after_failed_bracket(self):
        states = self.run_case()
        self.assertIn("EMERGENCY_FLATTEN_VERIFIED_FLAT", states)
        self.assertNotIn("CRITICAL_UNPROTECTED_POSITION_MANUAL_INTERVENTION", states)

    def test_residual_position_is_critical(self):
        states = self.run_case(residual=True)
        self.assertIn("CRITICAL_UNPROTECTED_POSITION_MANUAL_INTERVENTION", states)
        self.assertNotIn("EMERGENCY_FLATTEN_VERIFIED_FLAT", states)

    def test_remaining_algo_is_critical(self):
        states = self.run_case(stale_algo=True)
        self.assertIn("CRITICAL_UNPROTECTED_POSITION_MANUAL_INTERVENTION", states)
        self.assertNotIn("EMERGENCY_FLATTEN_VERIFIED_FLAT", states)


if __name__ == "__main__":
    unittest.main()
