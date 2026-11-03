"""Sandbox-only research publisher. No execution messages, no trading."""
import json
import os
import sqlite3
import time
import boto3
from futures_engine.research_outbox import DB
from futures_engine.research_sqs_preview import preview
from futures_engine.sandbox_hmac import sign
from futures_engine.sandbox_secret import load_key

QUEUE = "https://sqs.il-central-1.amazonaws.com/514349355336/signalpilot-signals-sandbox"

def publish(*, db=DB, sqs=None, now=None):
    if os.environ.get("SIGNALPILOT_SANDBOX_PUBLISH_ENABLED") != "1":
        raise RuntimeError("sandbox publisher disabled; explicit environment opt-in required")
    now = int(time.time()) if now is None else int(now)
    key = load_key()  # Fail closed before any send or publish claim.
    sqs = sqs or boto3.client("sqs", region_name="il-central-1")
    stats = {"sent": 0, "expired_or_blocked": 0, "already_sent": 0}
    with sqlite3.connect(db, timeout=20) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS sandbox_publish_log "
                     "(signal_id TEXT PRIMARY KEY, message_id TEXT NOT NULL, sent_at INTEGER NOT NULL)")
        rows = conn.execute("SELECT signal_id,symbol,candle_ms,state,payload "
                            "FROM research_outbox ORDER BY candle_ms ASC LIMIT 100").fetchall()
        for sid, symbol, candle, state, raw in rows:
            if conn.execute("SELECT 1 FROM sandbox_publish_log WHERE signal_id=?", (sid,)).fetchone():
                stats["already_sent"] += 1
                continue
            record = {"signal_id":sid, "symbol":symbol, "candle_ms":candle,
                      "state":state, "payload":json.loads(raw)}
            try:
                checked = preview(record, now=now)
            except ValueError:
                stats["expired_or_blocked"] += 1
                continue
            # Deliberately NOT the production inbox schema; no consumer can execute it.
            body = {"type":"SIGNALPILOT_SANDBOX_RESEARCH",
                    "research_signal_id":sid,
                    "candidate":checked["payload"],
                    "execution_authorized":False, "orders_enabled":False}
            body = sign(body, secret=key, now=int(time.time()))
            # Persist a claim BEFORE network I/O. If send result is ambiguous,
            # never retry automatically; operator must reconcile SQS first.
            conn.execute("INSERT INTO sandbox_publish_log VALUES (?,?,?)",
                         (sid,"UNCONFIRMED",int(time.time())))
            conn.commit()
            response = sqs.send_message(
                QueueUrl=QUEUE,
                MessageBody=json.dumps(body,sort_keys=True),
                MessageAttributes={"purpose":{"DataType":"String","StringValue":"research-only"}})
            conn.execute("UPDATE sandbox_publish_log SET message_id=?, sent_at=? WHERE signal_id=?",
                         (response["MessageId"],int(time.time()),sid))
            conn.commit()
            stats["sent"] += 1
    return stats

if __name__=="__main__":
    print(json.dumps(publish(),sort_keys=True))
