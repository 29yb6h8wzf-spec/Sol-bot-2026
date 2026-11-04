"""Tests for the no-network local archive adapter."""
import csv
import pytest
from futures_engine.offline_binance_csv import load_public_klines, replay_from_local_csv

T = 1793738100000

def write(path, rows):
    with path.open("w", newline="") as f:
        csv.writer(f).writerows(rows)

def plan():
    return {"signal_id":"synthetic-csv", "symbol":"SOLUSDT",
            "status":"INDICATIVE_PLAN_ONLY_NOT_EXECUTABLE",
            "orders_sent":False,"execution_authorized":False,
            "risk_snapshot_approved":False,"side":"long",
            "entry":"100","stop":"99","target":"102",
            "quantity":"1","closed_5m_candle_ms":T}

def test_local_archive_replay_is_hypothetical(tmp_path):
    p = tmp_path/"candles.csv"
    write(p, [["open_time","open","high","low","close","volume"],
              [T,100,102.5,99.8,102,123]])
    result = replay_from_local_csv(
        plan=plan(), csv_path=p, symbol="SOLUSDT",
        fetched_at_ms=T+600000, closed_through_ms=T+300000,
        journal_path=tmp_path/"paper.sqlite3")
    assert result["summary"]["closed_hypothetical"] == 1
    assert result["archive_authenticity_verified"] is False
    assert result["orders_sent"] is False

def test_microsecond_timestamp_rejected(tmp_path):
    p = tmp_path/"candles.csv"
    write(p, [[T*1000,100,101,99,100]])
    with pytest.raises(ValueError, match="millisecond"):
        load_public_klines(p, fetched_at_ms=T+600000,
                           closed_through_ms=T+300000)

def test_empty_archive_rejected(tmp_path):
    p = tmp_path/"candles.csv"
    write(p, [])
    with pytest.raises(ValueError, match="empty"):
        load_public_klines(p, fetched_at_ms=T+600000,
                           closed_through_ms=T+300000)

def test_bad_symbol_rejected_before_file_access(tmp_path):
    with pytest.raises(ValueError, match="symbol"):
        replay_from_local_csv(
            plan=plan(), csv_path=tmp_path/"missing.csv", symbol="ADAUSDT",
            fetched_at_ms=T+600000, closed_through_ms=T+300000,
            journal_path=tmp_path/"paper.sqlite3")
