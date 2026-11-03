"""Offline end-to-end outbox exercise. Uses synthetic data and a temporary database.

Never imports exchange clients, accesses SQS, or submits orders.
"""
import json
import os
import sqlite3
import tempfile
from unittest.mock import patch

from futures_engine.research_outbox import stage
from futures_engine.candidate_verifier import verify_candidate

SYMBOL = "SOL/USDT:USDT"
FIVE_STEP = 300000
FOUR_STEP = 14400000

def candles(step):
    return [
        {"time": 1800000000000 + i * step,
         "high": 102.0, "low": 98.0, "close": 100.0, "volume": 10.0}
        for i in range(110)
    ]

def run():
    five, four = candles(FIVE_STEP), candles(FOUR_STEP)
    candidate = {"strategy": "EMA_ADX", "direction": "LONG",
                 "score": 90, "reason": "synthetic fixture only"}
    with patch("futures_engine.candidate_verifier.candidates",
               return_value=([candidate], {})):
        verification = verify_candidate(candidate, symbol=SYMBOL, five=five, four=four)
    result = {
        "status": "RESEARCH_ONLY", "symbol": SYMBOL,
        "closed_5m_candle_ms": five[-1]["time"],
        "candidates_85_plus": [{**candidate, "verification": verification}],
    }
    with tempfile.TemporaryDirectory(prefix="signalpilot-outbox-test-") as directory:
        path = os.path.join(directory, "isolated.sqlite3")
        first = stage(result, db=path)
        second = stage(result, db=path)
        with sqlite3.connect(path) as db:
            count, state = db.execute(
                "SELECT COUNT(*), MIN(state) FROM research_outbox"
            ).fetchone()
    outcome = {
        "mode": "SYNTHETIC_OFFLINE_ONLY",
        "first_insert": first,
        "duplicate_insert": second,
        "outbox_count": count,
        "state": state,
        "sqs_sent": False,
        "orders_sent": False,
    }
    print(json.dumps(outcome, sort_keys=True))
    if (first, second, count, state) != (1, 0, 1, "PENDING_REVIEW"):
        raise SystemExit("FAIL: outbox invariant")
    print("PASS: offline end-to-end research outbox test")

if __name__ == "__main__":
    run()
