"""Offline checks for read-only research to paper planning bridge."""
import json
import sqlite3
from research_paper_bridge import run

CANDLE = 1793738100000
NOW = (CANDLE + 300000) // 1000 + 30

def record(sid="research-test", authorized=False):
    return (sid, "SOL/USDT:USDT", CANDLE, "PENDING_REVIEW", json.dumps({
        "signal_id": sid, "symbol": "SOL/USDT:USDT", "candle_ms": CANDLE,
        "strategy": "EMA_ADX", "direction": "SHORT", "score": 89,
        "status": "RECALCULATED_RESEARCH_CANDIDATE",
        "score_verified_independently": True,
        "execution_authorized": authorized, "sqs_sent": False,
        "orders_sent": False}))

def setup(path, rows):
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE research_outbox (signal_id TEXT,symbol TEXT,candle_ms INTEGER,state TEXT,payload TEXT)")
        db.executemany("INSERT INTO research_outbox VALUES (?,?,?,?,?)", rows)

def valid_plan(payload):
    return {
        "signal_id": payload["signal_id"],
        "symbol": payload["symbol"],
        "side": payload["direction"],
        "closed_5m_candle_ms": payload["closed_5m_candle_ms"],
        "status": "INDICATIVE_PLAN_ONLY_NOT_EXECUTABLE",
        "orders_sent": False,
        "execution_authorized": False,
        "risk_snapshot_approved": False,
        "entry": "100", "stop": "101", "target": "98",
        "quantity": "1", "estimated_loss_including_buffer": "1.20",
        "estimated_notional": "100",
    }


def test_plan_once(tmp_path):
    source, journal = tmp_path/"source.db", tmp_path/"journal.db"
    setup(source, [record()])
    calls = []
    def planner(payload, *, now_ms):
        calls.append(payload)
        return valid_plan(payload)
    a = run(source, journal, now=NOW, planner=planner)
    b = run(source, journal, now=NOW, planner=planner)
    assert a["planned"] == 1 and a["orders_sent"] is False
    assert b["already_seen"] == 1 and len(calls) == 1
    assert calls[0]["direction"] == "short"
    assert calls[0]["closed_5m_candle_ms"] == CANDLE

def test_stale_and_tampered(tmp_path):
    source, journal = tmp_path/"source.db", tmp_path/"journal.db"
    setup(source, [record(), record("research-tampered", authorized=True)])
    calls = []
    a = run(source, journal, now=NOW+150, planner=lambda *a, **k: calls.append(1))
    assert a["blocked"] == 2 and not calls

def test_no_executable_plans(tmp_path):
    source, journal = tmp_path/"source.db", tmp_path/"journal.db"
    setup(source, [record()])
    a = run(source, journal, now=NOW, planner=lambda p, **k: {
        "signal_id":p["signal_id"],"orders_sent":True,"execution_authorized":True})
    assert a["planned"] == 0 and a["blocked"] == 1

def test_incomplete_plan_blocked(tmp_path):
    source, journal = tmp_path/"source.db", tmp_path/"journal.db"
    setup(source, [record()])
    a = run(source, journal, now=NOW, planner=lambda p, **k: {
        "signal_id": p["signal_id"], "orders_sent": False,
        "execution_authorized": False})
    assert a["planned"] == 0 and a["blocked"] == 1


def test_wrong_side_and_risk_blocked(tmp_path):
    source, journal = tmp_path/"source.db", tmp_path/"journal.db"
    setup(source, [record("wrong-side"), record("excess-risk")])
    def planner(p, **kwargs):
        result = valid_plan(p)
        if p["signal_id"] == "wrong-side":
            result["side"] = "long"
        else:
            result["estimated_loss_including_buffer"] = "1.51"
        return result
    a = run(source, journal, now=NOW, planner=planner)
    assert a["planned"] == 0 and a["blocked"] == 2


def test_nonfinite_plan_blocked(tmp_path):
    source, journal = tmp_path/"source.db", tmp_path/"journal.db"
    setup(source, [record()])
    def planner(p, **kwargs):
        result = valid_plan(p)
        result["quantity"] = "NaN"
        return result
    a = run(source, journal, now=NOW, planner=planner)
    assert a["planned"] == 0 and a["blocked"] == 1
