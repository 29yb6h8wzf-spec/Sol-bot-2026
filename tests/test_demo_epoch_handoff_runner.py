"""Inbox-to-epoch readiness is read-only and rejects stale or fake signals."""
import json
import sqlite3
import demo_epoch_handoff_runner as runner
from test_demo_execution_gate import evidence, NOW


def inbox(tmp_path, items):
    path = tmp_path / "inbox.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE signals (signal_id TEXT, payload TEXT, received_at INTEGER)")
        for i, payload in enumerate(items):
            db.execute("INSERT INTO signals VALUES (?,?,?)",
                       (payload["signal_id"], json.dumps(payload), NOW - i))
    return path


def test_stale_inbox_does_not_touch_exchange_or_epoch(tmp_path):
    signal = evidence()[0]
    signal["timestamp"] = NOW - 500
    path = inbox(tmp_path, [signal])
    def forbidden(*args, **kwargs):
        raise AssertionError("should not connect for stale signal")
    result = runner.observe_once(path, now=NOW, exchange_factory=forbidden,
                                 refresh=forbidden)
    assert result["status"] == "NO_FRESH_VERIFIED_SIGNAL"
    assert result["orders_sent"] is False


def test_fresh_inbox_flows_to_verified_handoff_only(tmp_path):
    signal = evidence()[0]
    path = inbox(tmp_path, [signal])
    class Exchange:
        def close(self):
            pass
        def create_order(self, *a, **kw):
            raise AssertionError("must not submit orders")
    calls = []
    def refresh(*a, **kw):
        calls.append("refresh")
        return {"status": "EPOCH_RISK_RECONCILED"}
    def prepare(payload, exchange, **kwargs):
        calls.append("prepare")
        assert payload["signal_id"] == signal["signal_id"]
        return {"intent": {"signal_id": signal["signal_id"],
                           "symbol": "SOL/USDT:USDT", "event_key": "abc"}}
    result = runner.observe_once(path, now=NOW,
                                 exchange_factory=Exchange, refresh=refresh,
                                 prepare_handoff=prepare)
    assert result["status"] == "HANDOFF_READY_NOT_SUBMITTED"
    assert result["ready"] == 1
    assert result["execution_authorized"] is False
    assert calls == ["refresh", "prepare"]


def test_no_ready_when_independent_verifier_rejects(tmp_path):
    signal = evidence()[0]
    path = inbox(tmp_path, [signal])
    class Exchange:
        def close(self):
            pass
    def prepare(*a, **kw):
        raise ValueError("independent_candidate_mismatch")
    result = runner.observe_once(
        path, now=NOW, exchange_factory=Exchange,
        refresh=lambda *a, **kw: {"status": "EPOCH_RISK_RECONCILED"},
        prepare_handoff=prepare)
    assert result["status"] == "NO_ELIGIBLE_VERIFIED_SIGNAL"
    assert result["ready"] == 0
    assert result["blocked_reasons"]["independent_candidate_mismatch"] == 1


def test_utc_rollover_selects_new_immutable_baseline():
    from demo_epoch_handoff import epoch_paths
    day1 = epoch_paths(1794267500)
    day2 = epoch_paths(1794267500 + 86400)
    assert day1 != day2
    assert day1[0].endswith("2026-11-09.json")
    assert day2[0].endswith("2026-11-10.json")
