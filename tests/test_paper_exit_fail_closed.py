"""Fail-closed validation for simulation-only ledger exits."""
import pytest
from decimal import Decimal as D
from futures_engine.paper import PaperLedger


@pytest.mark.parametrize("fee,slip", [
    ("NaN", "0"), ("Infinity", "0"), ("-0.01", "0"), ("0", "-0.01")
])
def test_invalid_costs_do_not_close_position(tmp_path, fee, slip):
    ledger = PaperLedger(tmp_path / "paper.json")
    ledger.open_position({"side": "long", "entry": "100", "stop": "98",
                          "target": "104", "quantity": "1"}, 300000)
    with pytest.raises(ValueError, match="invalid paper execution costs"):
        ledger.evaluate_exit([[600000,100,105,97,100,1]], fee, slip)
    assert ledger.state["position"] is not None


@pytest.mark.parametrize("bar", [
    [600000, 100, float("nan"), 97, 100, 1],
    [600000, 100, 105, 97, 100, -1],
    [600000, 100, 101, 102, 100, 1],
    [600000, 100, 105],
])
def test_invalid_candle_does_not_close_position(tmp_path, bar):
    ledger = PaperLedger(tmp_path / "paper.json")
    ledger.open_position({"side": "long", "entry": "100", "stop": "98",
                          "target": "104", "quantity": "1"}, 300000)
    with pytest.raises((ValueError, TypeError)):
        ledger.evaluate_exit([bar], D("0.0006"), D("0.0005"))
    assert ledger.state["position"] is not None
