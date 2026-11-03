"""Offline-only inspection of staged research candidates. No SQS or orders."""
import json
import sqlite3
from datetime import datetime, timezone
from futures_engine.research_outbox import DB

def main():
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as db:
        rows=db.execute(
            "SELECT signal_id,symbol,candle_ms,state,payload "
            "FROM research_outbox ORDER BY candle_ms DESC LIMIT 10"
        ).fetchall()
    for sid,symbol,candle,state,raw in rows:
        p=json.loads(raw)
        print(json.dumps({
            "signal_id":sid,"symbol":symbol,
            "candle_utc":datetime.fromtimestamp(candle/1000,timezone.utc).isoformat(),
            "state":state,"score":p.get("score"),
            "strategy":p.get("strategy"),
            "direction":p.get("direction"),
            "status":p.get("status"),
            "execution_authorized":p.get("execution_authorized"),
            "sqs_sent":p.get("sqs_sent"),
            "orders_sent":p.get("orders_sent")
        },sort_keys=True))
    print("TOTAL_SHOWN:",len(rows))
if __name__=="__main__":
    main()
