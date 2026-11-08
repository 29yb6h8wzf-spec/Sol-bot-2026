"""Offline-only ATR stop and time-exit tests."""
from decimal import Decimal as D
import pytest
from futures_engine.core import Config, atr, plan_trade
from futures_engine.paper import PaperLedger


def bars(n=30):
    return [[i*900000, "100", "101", "99", "100", "10"] for i in range(n)]


def test_atr14_constant_range():
    assert atr(bars(), 14) == D("2")


def test_atr_based_stop_and_target_respect_risk(tmp_path):
    cfg = Config(atr_stop_multiple=D("1.5"), atr_reward_multiple=D("2"),
                 taker_fee=D("0.0005"), slippage_fraction=D("0.0003"))
    distance = atr(bars(), cfg.atr_period) * cfg.atr_stop_multiple / D("100")
    plan = plan_trade(cfg, "long", "100", "37.50", "37.50",
                      amount_step=D("0.001"), stop_fraction_override=distance)
    assert D(plan["stop"]) == D("97")
    assert D(plan["target"]) == D("106")
    assert D(plan["max_estimated_loss"]) <= D("0.375")
    assert D(plan["margin_estimate"]) <= D("37.50")


def test_time_exit_with_fees_and_slippage(tmp_path):
    ledger = PaperLedger(tmp_path / "ledger.json", D("37.50"))
    plan = {"side":"long","entry":"100","stop":"97","target":"106",
            "quantity":"0.1","margin_estimate":"5","max_estimated_loss":"0.316"}
    ledger.open_position(plan, 0)
    candle = [[900000,"100","101","99","100","10"]]
    event = ledger.evaluate_exit(candle, D("0.0005"), D("0.0003"), 15, 15)
    assert event["reason"] == "time"
    assert event["timestamp"] == 900000
    assert D(event["pnl"]) == D("-0.016")
    assert ledger.state["position"] is None
    assert len(ledger.state["history"]) == 2


def test_stop_precedes_time_exit_when_both_trigger(tmp_path):
    ledger = PaperLedger(tmp_path / "ledger.json", D("37.50"))
    ledger.open_position({"side":"long","entry":"100","stop":"97","target":"106",
                          "quantity":"0.1","margin_estimate":"5",
                          "max_estimated_loss":"0.316"}, 0)
    event = ledger.evaluate_exit([[900000,"100","101","96","100","10"]],
                                 D("0.0005"), D("0.0003"), 15, 15)
    assert event["reason"] == "stop"


def test_atr_safety_bound_rejects_too_wide_stop():
    cfg = Config()
    with pytest.raises(ValueError, match="ATR stop outside"):
        plan_trade(cfg, "long", 100, D("37.50"), D("37.50"),
                   stop_fraction_override=D("0.06"))
