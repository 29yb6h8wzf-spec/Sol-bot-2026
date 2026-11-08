"""Crash-window recovery: no orders or market requests."""
import json
import pytest
from decimal import Decimal
from futures_engine import __main__ as scanner
from futures_engine.paper import PaperLedger


def test_crash_between_atomic_ledger_commit_and_audit_write(tmp_path, monkeypatch, capsys):
    path = tmp_path / "paper-ledger-sol.json"
    audit = tmp_path / "paper-ledger-sol.audit.json"
    bars = [[i * 900000, 100, 101, 99, 100, 10] for i in range(239)]
    class Exchange:
        def close(self):
            pass
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.setenv("FUTURES_SYMBOL", "SOL/USDT:USDT")
    monkeypatch.setenv("PAPER_LEDGER", str(path))
    monkeypatch.setenv("PAPER_AUDIT_PATH", str(audit))
    monkeypatch.setenv("PAPER_START_EQUITY", "37.50")
    monkeypatch.setattr(scanner, "closed_futures_bars", lambda *args: (Exchange(), {}, bars))
    original = scanner.sync_ledger
    calls = {"count": 0}
    def crash_after_commit(*args):
        calls["count"] += 1
        if calls["count"] == 2:
            raise SystemExit("simulated process termination after ledger commit")
        return original(*args)
    monkeypatch.setattr(scanner, "sync_ledger", crash_after_commit)
    with pytest.raises(SystemExit, match="simulated process termination"):
        scanner.main()
    persisted = json.loads(path.read_text())
    assert persisted["last_processed_candle"] == bars[-1][0]
    assert persisted["scan_reason_days"]["1970-01-03"]["no_cross"] == 1
    monkeypatch.setattr(scanner, "sync_ledger", original)
    scanner.main()
    output = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert output["evaluated"] is False
    assert output["stop_reason"] == "duplicate_closed_candle"
    persisted = json.loads(path.read_text())
    assert sum(d["no_cross"] for d in persisted["scan_reason_days"].values()) == 1
    assert json.loads(audit.read_text())["last_closed_candle"] == bars[-1][0]
    assert persisted["position"] is None


def test_crash_before_commit_has_no_persisted_partial_entry(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = PaperLedger(path, Decimal("37.50"))
    assert ledger.begin_scan(900000)
    plan = {"side": "long", "entry": "100", "stop": "99", "target": "102",
            "quantity": "0.1", "margin_estimate": "5", "max_estimated_loss": "0.1"}
    ledger.open_position(plan, 900000)
    # Simulated SIGKILL: discard object without calling commit_scan.
    recovered = PaperLedger(path, Decimal("37.50"))
    assert recovered.state["position"] is None
    assert recovered.state["history"] == []
    assert recovered.begin_scan(900000)
    recovered.open_position(plan, 900000)
    recovered.commit_scan(900000, "signal")
    again = PaperLedger(path, Decimal("37.50"))
    assert again.begin_scan(900000) is False
    assert len(again.state["history"]) == 1
    assert again.state["position"]["signal_candle"] == 900000

def test_real_child_process_termination_after_ledger_commit(tmp_path):
    """Hard process termination, not an exception; recover from disk."""
    import os
    import subprocess
    import sys
    path = tmp_path / "child-ledger.json"
    script = """
import os, sys
from decimal import Decimal
from futures_engine.paper import PaperLedger
ledger = PaperLedger(sys.argv[1], Decimal('37.50'))
assert ledger.begin_scan(900000)
ledger.open_position({'side':'long','entry':'100','stop':'99','target':'102',
                      'quantity':'0.1','margin_estimate':'5',
                      'max_estimated_loss':'0.1'}, 900000)
ledger.commit_scan(900000, 'signal')
os._exit(73)
"""
    env = dict(os.environ)
    child = subprocess.run([sys.executable, "-c", script, str(path)],
                           env=env, capture_output=True, text=True)
    assert child.returncode == 73, child.stderr
    recovered = PaperLedger(path, Decimal("37.50"))
    assert recovered.begin_scan(900000) is False
    assert recovered.state["position"]["signal_candle"] == 900000
    assert len(recovered.state["history"]) == 1
    assert sum(v["signal"] for v in recovered.state["scan_reason_days"].values()) == 1
