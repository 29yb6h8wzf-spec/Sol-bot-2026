"""Offline fail-closed tests: no exchange calls or orders."""
import sqlite3
import time
from signal_inbox import accept
from demo_signal_router import connect_inbox


def payload(sid, score=85):
    return dict(signal_id=sid, symbol="XRPUSDT", direction="long",
                score=score, timestamp=int(time.time()),
                source="verified_85_score_engine")


def test_independent_score_overrides_incoming_score(tmp_path):
    inbox = str(tmp_path / "inbox.sqlite3")
    journal = str(tmp_path / "route.sqlite3")
    assert accept(payload("score-recheck-001", 100), db=inbox)
    rows = connect_inbox(
        inbox, journal,
        verifier=lambda p: dict(signal_id=p["signal_id"],
                                symbol="XRP/USDT:USDT",
                                score=84, source="verified_85_score_engine"),
        preflight=lambda v, a: (True, "ok"),
        account={"equity": "150"})
    assert len(rows) == 1
    assert rows[0]["status"] == "REJECTED"
    assert rows[0]["reason"] == "score_below_85"
    assert rows[0]["orders_sent"] is False


def test_verifier_exception_blocks_without_preflight(tmp_path):
    inbox = str(tmp_path / "inbox.sqlite3")
    journal = str(tmp_path / "route.sqlite3")
    assert accept(payload("verifier-error-001"), db=inbox)

    def broken_verifier(_):
        raise RuntimeError("market_data_unavailable")

    def forbidden_preflight(*_):
        raise AssertionError("preflight_must_not_run")

    rows = connect_inbox(inbox, journal, verifier=broken_verifier,
                         preflight=forbidden_preflight,
                         account={"equity": "150"})
    assert rows[0]["status"] == "BLOCKED_VERIFICATION_ERROR"
    assert rows[0]["reason"] == "RuntimeError"
    assert rows[0]["orders_sent"] is False
    assert connect_inbox(inbox, journal) == []
    with sqlite3.connect(journal) as db:
        assert db.execute("SELECT COUNT(*) FROM demo_signal_route").fetchone()[0] == 1
