"""Replay refuses malformed chronology before creating a durable trade."""
import pytest

from research.paper_market_replay import replay


def payload():
    return {
        "symbol": "SOLUSDT", "signal_uid": "chronology-1",
        "side": "LONG", "quantity": "1", "entry_mid": "100",
        "stop": "98", "target": "104", "opened_at": 1700000000,
        "bars": [
            {"open_ms": 1700000000000, "close_ms": 1700000299999,
             "high": "102", "low": "99", "close": "101",
             "confirmed_closed": True},
            {"open_ms": 1700000300000, "close_ms": 1700000599999,
             "high": "105", "low": "100", "close": "104",
             "confirmed_closed": True},
        ],
    }


@pytest.mark.parametrize("second_open", [1700000000000, 1700000299999, 1699999999999])
def test_rejects_duplicate_overlap_or_reversal_before_db_write(tmp_path, second_open):
    case = payload()
    case["bars"][1]["open_ms"] = second_open
    db = tmp_path / "chronology.sqlite3"
    with pytest.raises(ValueError, match="non-monotonic"):
        replay(case, str(db))
    assert not db.exists()


def test_valid_chronology_executes_paper_target(tmp_path):
    result = replay(payload(), str(tmp_path / "valid.sqlite3"))
    assert result["trade"]["status"] == "EXECUTED_TP"


@pytest.mark.parametrize("field,value,reason", [
    ("confirmed_closed", False, "unconfirmed"),
    ("high", "NaN", "invalid paper OHLC"),
    ("low", "0", "invalid paper OHLC"),
    ("close", "200", "invalid paper OHLC"),
])
def test_rejects_late_malformed_candle_before_opening_trade(tmp_path, field, value, reason):
    case = payload()
    case["bars"][1][field] = value
    db = tmp_path / "no-phantom-paper.sqlite3"
    with pytest.raises(ValueError, match=reason):
        replay(case, str(db))
    assert not db.exists()


def test_rejects_pre_entry_bar_before_sqlite_write(tmp_path):
    case = payload()
    case["opened_at"] += 300
    db = tmp_path / "pre-entry.sqlite3"
    with pytest.raises(ValueError, match="precedes trade entry"):
        replay(case, str(db))
    assert not db.exists()
