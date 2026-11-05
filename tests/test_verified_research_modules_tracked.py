"""Offline regression tests for the research modules promoted from AWS."""
import json
import sqlite3

import pytest

from futures_engine.candidate_verifier import verify_candidate, VerificationError
from futures_engine.research_history import record
from futures_engine.verified_candidate_audit import audit_candidate


def candles(interval, last_ms, length=120):
    start=last_ms-(length-1)*interval
    return [[start+i*interval,100,101,99,100,10] for i in range(length)]


def strategy_candles(interval, length=120):
    return [{"time":i*interval, "high":101.0, "low":99.0,
             "close":100.0, "volume":10.0} for i in range(length)]


def test_verified_candidate_blocks_unknown_strategy_and_mismatch():
    five=strategy_candles(300000)
    four=strategy_candles(14400000)
    with pytest.raises(VerificationError, match="unknown strategy"):
        verify_candidate({"strategy":"E2E_SYNTHETIC_TEST",
                          "direction":"LONG","score":85},
                         symbol="SOL/USDT:USDT",five=five,four=four)
    with pytest.raises(VerificationError, match="claimed candidate"):
        verify_candidate({"strategy":"MACD_VOLUME",
                          "direction":"LONG","score":85},
                         symbol="SOL/USDT:USDT",five=five,four=four)


def test_verified_candidate_identity_is_deterministic_and_non_executable(monkeypatch):
    from futures_engine import candidate_verifier as verifier
    monkeypatch.setattr(verifier,"candidates",lambda five,four: (
        [{"strategy":"MACD_VOLUME","direction":"SHORT","score":85}],{}))
    five=strategy_candles(300000)
    four=strategy_candles(14400000)
    candidate={"strategy":"MACD_VOLUME","direction":"SHORT","score":85}
    a=verifier.verify_candidate(candidate,symbol="XRP/USDT:USDT",
                                five=five,four=four)
    b=verifier.verify_candidate(candidate,symbol="XRP/USDT:USDT",
                                five=five,four=four)
    assert a==b
    assert a["score_verified_independently"] is True
    assert a["execution_authorized"] is False
    assert a["orders_sent"] is False and a["sqs_sent"] is False
    assert a["signal_id"].startswith("research-")


def test_readonly_audit_checks_closed_candle_and_gaps():
    now=1_800_000_000_000
    last=(now//300000-1)*300000
    data=candles(300000,last)
    result=audit_candidate("BTC/USDT:USDT",data,None,
                            now_ms=now,timeframe_ms=300000)
    assert result["status"]=="NO_SIGNAL"
    assert result["orders_sent"] is False
    data[-2][0]+=1
    with pytest.raises(ValueError,match="misaligned|noncontiguous"):
        audit_candidate("BTC/USDT:USDT",data,None,
                        now_ms=now,timeframe_ms=300000)


def test_research_history_writes_only_local_non_executable_rows(tmp_path):
    path=tmp_path/"research.sqlite3"
    row={"symbol":"BTC/USDT:USDT","status":"RESEARCH_ONLY",
         "closed_5m_candle_ms":300000,
         "sqs_sent":False,"orders_sent":False}
    assert record(row,db=str(path),observed_at=1000) is True
    with sqlite3.connect(path) as db:
        saved=db.execute("SELECT symbol,candle_ms,status,payload "
                         "FROM research_scans").fetchall()
    assert len(saved)==1 and json.loads(saved[0][3])==row
    with pytest.raises(ValueError):
        record({**row,"orders_sent":True},db=str(path),observed_at=1001)
