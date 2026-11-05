"""Paper-only entry and restart safety: no exchange or order calls."""
from decimal import Decimal as D
import pytest
from futures_engine.paper import PaperLedger


def plan(**changes):
    p = {"side": "long", "entry": "100", "stop": "98", "target": "104",
         "quantity": "0.5"}
    p.update(changes)
    return p


@pytest.mark.parametrize("change", [
    {"entry": "NaN"}, {"entry": "Infinity"}, {"quantity": "-1"},
    {"quantity": "0"}, {"stop": "101"}, {"target": "99"},
    {"side": "other"}, {"entry": "0"}, {"stop": "NaN"},
])
def test_bad_entry_never_mutates_ledger(tmp_path, change):
    path = tmp_path / "ledger.json"
    ledger = PaperLedger(path, initial_equity=D("150"))
    with pytest.raises(ValueError):
        ledger.open_position(plan(**change), 300000)
    assert ledger.state["position"] is None
    assert not path.exists()


def test_paper_entry_exit_survives_restart_and_never_double_exits(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = PaperLedger(path, initial_equity=D("150"))
    ledger.open_position(plan(), 300000)
    restarted = PaperLedger(path)
    assert restarted.state["position"]["quantity"] == "0.5"
    event = restarted.evaluate_exit([[600000,100,105,97,100,1]], D("0.0006"), D("0.0005"))
    assert event["reason"] == "stop"
    assert event["pnl"] == "-1.1089"
    after = PaperLedger(path)
    assert after.state["position"] is None
    assert len(after.state["history"]) == 2
    assert after.evaluate_exit([[600000,100,105,97,100,1]], D("0.0006"), D("0.0005")) is None
    assert len(PaperLedger(path).state["history"]) == 2
