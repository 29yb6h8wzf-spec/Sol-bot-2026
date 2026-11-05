"""The Paper observer must be pure and accurately track real ledger transitions."""
import json
from decimal import Decimal

import pytest

from futures_engine.paper import PaperLedger
from futures_engine.paper_observer import summarize_ledger


def test_empty_paper_ledger_has_no_events(tmp_path):
    state = PaperLedger(tmp_path / "paper.json", Decimal("37.50")).state
    before = json.dumps(state, sort_keys=True)
    summary = summarize_ledger(state)
    assert summary == {
        "paper_entries": 0, "paper_exits": 0, "history_count": 0,
        "last_paper_event": None, "last_signal_candle": None}
    assert json.dumps(state, sort_keys=True) == before


def test_observer_follows_persisted_entry_exit_and_restart(tmp_path):
    path = tmp_path / "paper.json"
    ledger = PaperLedger(path, Decimal("37.50"))
    ledger.open_position({"side": "long", "entry": "100", "stop": "98",
                          "target": "104", "quantity": "0.16",
                          "max_estimated_loss": "0.36", "margin_estimate": "8"}, 300000)
    summary = summarize_ledger(PaperLedger(path).state)
    assert (summary["paper_entries"], summary["paper_exits"]) == (1, 0)
    assert summary["last_paper_event"] == {"event": "paper_entry", "candle_ms": 300000}
    assert summary["last_signal_candle"] == 300000
    restarted = PaperLedger(path)
    event = restarted.evaluate_exit([[1200000, 100, 105, 99, 104, 10]],
                                    Decimal("0.0006"), Decimal("0.0005"))
    assert event["reason"] == "target"
    final = summarize_ledger(PaperLedger(path).state)
    assert (final["paper_entries"], final["paper_exits"], final["history_count"]) == (1, 1, 2)
    assert final["last_paper_event"]["candle_ms"] == 1200000
    assert final["last_paper_event"]["reason"] == "target"
    assert final["last_paper_event"]["pnl"] == event["pnl"]


@pytest.mark.parametrize("state", [
    None,
    {"history": None},
    {"history": ["bad"]},
    {"history": [{"event": "unknown", "timestamp": 300000}]},
    {"history": [{"event": "paper_exit", "timestamp": 300000, "reason": "target"}]},
    {"history": [{"event": "paper_entry", "signal_candle": "300000"}]},
    {"history": [{"event": "paper_entry", "signal_candle": 300000}],
     "position": None},
    {"history": [], "position": "bad"},
    {"history": [], "last_signal_candle": -1},
])
def test_invalid_state_is_not_reported_as_clean(state):
    with pytest.raises(ValueError):
        summarize_ledger(state)
