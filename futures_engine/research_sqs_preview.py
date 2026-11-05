"""Research-only SQS payload preview. No network, no queue writes, no orders."""
import hashlib
import json
import sqlite3
import time
from futures_engine.research_outbox import DB, RESEARCH_STRATEGIES

SYMBOLS={"BTC/USDT:USDT":"BTCUSDT","ETH/USDT:USDT":"ETHUSDT",
         "SOL/USDT:USDT":"SOLUSDT","XRP/USDT:USDT":"XRPUSDT"}

def preview(record, *, now=None):
    now=int(time.time()) if now is None else int(now)
    if record.get("state")!="PENDING_REVIEW":
        raise ValueError("not pending")
    v=record["payload"]
    if (v.get("status")!="RECALCULATED_RESEARCH_CANDIDATE"
        or v.get("score_verified_independently") is not True
        or v.get("strategy") not in RESEARCH_STRATEGIES
        or v.get("execution_authorized") is not False
        or v.get("sqs_sent") is not False
        or v.get("orders_sent") is not False
        or v.get("symbol")!=record["symbol"]
        or v.get("candle_ms")!=record["candle_ms"]
        or v.get("signal_id")!=record["signal_id"]):
        raise ValueError("research verification mismatch")
    if record["symbol"] not in SYMBOLS or v.get("direction") not in ("LONG","SHORT"):
        raise ValueError("invalid market")
    if type(v.get("score")) is not int or not 85<=v["score"]<=95:
        raise ValueError("invalid score")
    if type(record["candle_ms"]) is not int or record["candle_ms"]%300000:
        raise ValueError("invalid candle timestamp")
    # Use candle close as event time; never stamp an old signal with current time.
    event_seconds=(record["candle_ms"]+300000)//1000
    if not 0<=now-event_seconds<=120:
        raise ValueError("expired or future research candidate")
    digest=hashlib.sha256(record["signal_id"].encode()).hexdigest()[:24]
    payload={"signal_id":"r-"+digest,"symbol":SYMBOLS[record["symbol"]],
             "direction":v["direction"].lower(),"score":v["score"],
             "timestamp":event_seconds,"source":"verified_85_score_engine"}
    return {"mode":"DRY_RUN_NO_SEND","payload":payload,
            "authenticated_source":False,"execution_authorized":False}

def main():
    with sqlite3.connect(f"file:{DB}?mode=ro",uri=True) as db:
        rows=db.execute(
            "SELECT signal_id,symbol,candle_ms,state,payload FROM research_outbox "
            "ORDER BY candle_ms DESC LIMIT 20").fetchall()
    for sid,symbol,candle,state,raw in rows:
        record={"signal_id":sid,"symbol":symbol,"candle_ms":candle,
                "state":state,"payload":json.loads(raw)}
        try:
            print(json.dumps(preview(record),sort_keys=True))
        except ValueError as exc:
            print(json.dumps({"signal_id":sid,"mode":"BLOCKED","reason":str(exc),
                              "sqs_sent":False,"orders_sent":False},sort_keys=True))
    print("INSPECTED:",len(rows),"SQS_SENT: 0","ORDERS_SENT: 0")

if __name__=="__main__":
    main()
