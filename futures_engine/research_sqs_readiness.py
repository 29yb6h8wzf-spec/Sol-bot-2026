"""Read-only SQS publishing readiness audit. No sends or orders."""
import json
import os
import sqlite3
from futures_engine.research_outbox import DB
from futures_engine.research_sqs_preview import preview

def audit(*, db=DB, now=None):
    if not os.path.isfile(db):
        return {"status":"BLOCKED","reason":"outbox database missing","sqs_sent":False}
    with sqlite3.connect(f"file:{db}?mode=ro",uri=True) as conn:
        rows=conn.execute("SELECT signal_id,symbol,candle_ms,state,payload "
                          "FROM research_outbox ORDER BY candle_ms DESC LIMIT 100").fetchall()
    ready=0
    expired=0
    invalid=0
    for sid,symbol,candle,state,raw in rows:
        try:
            item={"signal_id":sid,"symbol":symbol,"candle_ms":candle,
                  "state":state,"payload":json.loads(raw)}
            preview(item,now=now)
            ready+=1
        except ValueError as exc:
            if "expired or future" in str(exc):
                expired+=1
            else:
                invalid+=1
    return {"mode":"READ_ONLY","total_inspected":len(rows),
            "fresh_previewable":ready,"expired_or_future":expired,
            "invalid_or_not_pending":invalid,
            "sqs_sent":False,"orders_sent":False,
            "publisher_enabled":False}

if __name__=="__main__":
    print(json.dumps(audit(),sort_keys=True))
