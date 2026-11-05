"""Synthetic offline journal tests; never connect to an exchange."""
import pytest
from futures_engine.offline_replay_journal import record_result, summary

DIGEST = "a" * 64
DAY = "2026-11-04"
def closed(pnl="-1.20"):
    return {"status": "CLOSED_HYPOTHETICAL", "exit_reason": "STOP",
            "net_pnl_excluding_funding": pnl, "orders_sent": False}

def test_idempotent_and_summary(tmp_path):
    path = tmp_path / "paper.sqlite3"
    args = dict(signal_id="s1", history_sha256=DIGEST,
                replay_record=closed(), day_utc=DAY)
    assert record_result(path, **args)["inserted"]
    assert not record_result(path, **args)["inserted"]
    s = summary(path, day_utc=DAY)
    assert s["events"] == 1 and s["closed_hypothetical"] == 1
    assert s["realized_hypothetical_pnl_excluding_funding"] == "-1.20"
    assert s["orders_sent"] is False

def test_conflicting_replay_blocked(tmp_path):
    path = tmp_path / "paper.sqlite3"
    record_result(path, signal_id="s1", history_sha256=DIGEST,
                  replay_record=closed(), day_utc=DAY)
    with pytest.raises(ValueError, match="conflicting"):
        record_result(path, signal_id="s1", history_sha256=DIGEST,
                      replay_record=closed("-0.50"), day_utc=DAY)

def test_unknown_never_counts_as_profit(tmp_path):
    path = tmp_path / "paper.sqlite3"
    record_result(path, signal_id="s1", history_sha256=DIGEST,
                  replay_record={"status": "UNKNOWN", "orders_sent": False}, day_utc=DAY)
    s = summary(path, day_utc=DAY)
    assert s["unknown"] == 1 and s["realized_hypothetical_pnl_excluding_funding"] == "0"

def test_open_with_realized_pnl_blocked(tmp_path):
    with pytest.raises(ValueError, match="unclosed_pnl"):
        record_result(tmp_path/"paper.sqlite3", signal_id="s1",
                      history_sha256=DIGEST, day_utc=DAY,
                      replay_record={"status": "OPEN_HYPOTHETICAL",
                                     "net_pnl_excluding_funding": "10",
                                     "orders_sent": False})

def test_daily_cap_flag_is_not_authorization(tmp_path):
    path = tmp_path / "paper.sqlite3"
    record_result(path, signal_id="s1", history_sha256=DIGEST,
                  replay_record=closed("-7.50"), day_utc=DAY)
    s = summary(path, day_utc=DAY)
    assert s["daily_loss_cap_breached"] is True
    assert s["risk_authorization"] is False

def test_order_flag_rejected(tmp_path):
    with pytest.raises(ValueError):
        record_result(tmp_path/"paper.sqlite3", signal_id="s1",
                      history_sha256=DIGEST, day_utc=DAY,
                      replay_record={**closed(), "orders_sent": True})


def test_same_signal_different_day_is_conflict(tmp_path):
    path = tmp_path / "paper.sqlite3"
    record_result(path, signal_id="s1", history_sha256=DIGEST,
                  replay_record=closed(), day_utc=DAY)
    with pytest.raises(ValueError, match="conflicting_replay_for_signal"):
        record_result(path, signal_id="s1", history_sha256=DIGEST,
                      replay_record=closed(), day_utc="2026-11-05")


@pytest.mark.parametrize("invalid_day", ["2026-02-30", "2026-13-01",
                                         "2026-1-04", "not-a-date"])
def test_invalid_day_rejected(tmp_path, invalid_day):
    with pytest.raises(ValueError, match="invalid_day"):
        record_result(tmp_path / "paper.sqlite3", signal_id="s1",
                      history_sha256=DIGEST, replay_record=closed(),
                      day_utc=invalid_day)
