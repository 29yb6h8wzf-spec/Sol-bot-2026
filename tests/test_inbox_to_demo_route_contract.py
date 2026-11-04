"""Offline end-to-end intake -> independent verifier -> risk routing contract."""
import time

from signal_inbox import accept
from demo_signal_router import connect_inbox


def payload():
    return dict(signal_id="e2e-offline-001", symbol="XRPUSDT", direction="long",
                score=85, timestamp=int(time.time()), source="verified_85_score_engine")


def verified(p):
    return dict(signal_id=p["signal_id"], symbol="XRP/USDT:USDT",
                source="verified_85_score_engine", score=85)


def test_missing_independent_verifier_blocks_and_journals_once(tmp_path):
    inbox, journal = str(tmp_path / "inbox.sqlite"), str(tmp_path / "journal.sqlite")
    assert accept(payload(), db=inbox)
    assert not accept(payload(), db=inbox)
    result = connect_inbox(inbox, journal)
    assert len(result) == 1
    assert result[0]["status"] == "BLOCKED_UNVERIFIED"
    assert result[0]["orders_sent"] is False
    assert connect_inbox(inbox, journal) == []


def test_verified_but_missing_account_blocks(tmp_path):
    inbox, journal = str(tmp_path / "inbox.sqlite"), str(tmp_path / "journal.sqlite")
    assert accept(payload(), db=inbox)
    result = connect_inbox(inbox, journal, verifier=verified,
                           preflight=lambda v, a: (True, "ok"))
    assert result[0]["status"] == "BLOCKED_PREFLIGHT"
    assert result[0]["orders_sent"] is False


def test_rejected_risk_never_submits(tmp_path):
    inbox, journal = str(tmp_path / "inbox.sqlite"), str(tmp_path / "journal.sqlite")
    assert accept(payload(), db=inbox)
    result = connect_inbox(inbox, journal, verifier=verified,
                           preflight=lambda v, a: (False, "unreconciled_fills"),
                           account={"equity": "150"})
    assert result[0]["status"] == "REJECTED_RISK"
    assert result[0]["reason"] == "unreconciled_fills"
    assert result[0]["orders_sent"] is False


def test_approved_mock_is_only_eligible_not_submitted(tmp_path):
    inbox, journal = str(tmp_path / "inbox.sqlite"), str(tmp_path / "journal.sqlite")
    assert accept(payload(), db=inbox)
    result = connect_inbox(inbox, journal, verifier=verified,
                           preflight=lambda v, a: (True, "ok"),
                           account={"equity": "150"})
    assert result[0]["status"] == "DEMO_ELIGIBLE_NOT_SUBMITTED"
    assert result[0]["orders_sent"] is False


def test_transient_block_can_recover_without_duplicate_submission(tmp_path):
    inbox, journal = str(tmp_path / "inbox.sqlite"), str(tmp_path / "journal.sqlite")
    assert accept(payload(), db=inbox)
    first = connect_inbox(inbox, journal)
    assert first[0]["status"] == "BLOCKED_UNVERIFIED"
    recovered = connect_inbox(inbox, journal, verifier=verified,
                              preflight=lambda v, a: (True, "ok"),
                              account={"equity": "150"})
    assert len(recovered) == 1
    assert recovered[0]["status"] == "DEMO_ELIGIBLE_NOT_SUBMITTED"
    assert recovered[0]["orders_sent"] is False
    assert connect_inbox(inbox, journal, verifier=verified,
                         preflight=lambda v, a: (True, "ok"),
                         account={"equity": "150"}) == []


def test_risk_rejection_remains_terminal(tmp_path):
    inbox, journal = str(tmp_path / "inbox.sqlite"), str(tmp_path / "journal.sqlite")
    assert accept(payload(), db=inbox)
    rejected = connect_inbox(inbox, journal, verifier=verified,
                             preflight=lambda v, a: (False, "unreconciled_fills"),
                             account={"equity": "150"})
    assert rejected[0]["status"] == "REJECTED_RISK"
    assert connect_inbox(inbox, journal, verifier=verified,
                         preflight=lambda v, a: (True, "ok"),
                         account={"equity": "150"}) == []
