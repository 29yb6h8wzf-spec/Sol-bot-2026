"""Offline tests: preflight cannot place exchange orders."""
from dataclasses import replace
import unittest

from futures_engine.live_preflight import (
    OrderProposal, PreflightRejected, RiskPolicy, assess_order,
)


def valid():
    return OrderProposal(
        symbol="SOL/USDT:USDT", direction="long", quantity="1",
        entry_price="100", stop_price="99", take_profit_price="102",
        leverage="2", available_margin_usdt="150",
        realized_daily_loss_usdt="0", open_positions=0,
    )


class LivePreflightTests(unittest.TestCase):
    def test_approved_proposal_is_not_submitted(self):
        result = assess_order(valid())
        self.assertEqual(result["status"], "not_submitted")
        self.assertEqual(result["mode"], "offline_preflight_only")
        self.assertEqual(result["estimated_stop_loss_usdt"], "1.200")

    def test_rejects_excess_stop_risk(self):
        with self.assertRaises(PreflightRejected):
            assess_order(replace(valid(), stop_price="98"))

    def test_rejects_insufficient_margin(self):
        with self.assertRaises(PreflightRejected):
            assess_order(replace(valid(), available_margin_usdt="49"))

    def test_rejects_leverage_over_two(self):
        with self.assertRaises(PreflightRejected):
            assess_order(replace(valid(), leverage="3"))

    def test_rejects_existing_position(self):
        for count in (1, -1, True):
            with self.subTest(count=count), self.assertRaises(PreflightRejected):
                assess_order(replace(valid(), open_positions=count))

    def test_rejects_daily_loss_exhausted(self):
        for loss in ("7.5", "7", "NaN", "-1"):
            with self.subTest(loss=loss), self.assertRaises(PreflightRejected):
                assess_order(replace(valid(), realized_daily_loss_usdt=loss))

    def test_rejects_invalid_stop_or_target(self):
        for changes in (
            {"stop_price": "101"}, {"take_profit_price": "99"},
            {"entry_price": "Infinity"}, {"quantity": "0"},
            {"quantity": "NaN"}, {"symbol": "DOGE/USDT:USDT"},
            {"direction": "buy"}, {"leverage": "0"},
        ):
            with self.subTest(changes=changes), self.assertRaises(PreflightRejected):
                assess_order(replace(valid(), **changes))

    def test_short_side_rules(self):
        short = replace(valid(), direction="short", stop_price="101",
                        take_profit_price="98")
        self.assertEqual(assess_order(short)["status"], "not_submitted")
        with self.assertRaises(PreflightRejected):
            assess_order(replace(short, stop_price="99"))

    def test_notional_cap(self):
        with self.assertRaises(PreflightRejected):
            assess_order(replace(valid(), quantity="4"))

    def test_invalid_policy_rejected(self):
        for policy in (RiskPolicy(max_daily_loss_pct="0"),
                       RiskPolicy(round_trip_cost_rate="-1"),
                       RiskPolicy(starting_capital_usdt="NaN")):
            with self.subTest(policy=policy), self.assertRaises(PreflightRejected):
                assess_order(valid(), policy)


if __name__ == "__main__":
    unittest.main()
