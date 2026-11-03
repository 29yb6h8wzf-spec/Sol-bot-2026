"""Sandbox research-only SQS consumer. Never calls trading or production inbox."""
import json
import os
import sqlite3
import time
import boto3
from futures_engine.sandbox_hmac import verify
from futures_engine.sandbox_secret import load_key

QUEUE = "https://sqs.il-central-1.amazonaws.com/514349355336/signalpilot-signals-sandbox"
DB = "/opt/signalpilot/sandbox-received.sqlite3"
SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"}

def validate(body):
    if not isinstance(body, dict) or set(body) != {
        "type", "research_signal_id", "candidate", "execution_authorized", "orders_enabled"
    }:
        raise ValueError("invalid envelope")
    if body["type"] != "SIGNALPILOT_SANDBOX_RESEARCH":
        raise ValueError("invalid message type")
    if body["execution_authorized"] is not False or body["orders_enabled"] is not False:
        raise ValueError("orders not disabled")
    sid = body["research_signal_id"]
    if not isinstance(sid, str) or not sid.startswith("research-") or len(sid) > 64:
        raise ValueError("invalid research id")
    p = body["candidate"]
    if not isinstance(p, dict) or set(p) != {
        "signal_id", "symbol", "direction", "score", "timestamp", "source"
    }:
        raise ValueError("invalid candidate schema")
    if p["symbol"] not in SYMBOLS or p["direction"] not in ("long", "short"):
        raise ValueError("invalid market")
    if type(p["score"]) is not int or not 85 <= p["score"] <= 95:
        raise ValueError("invalid score")
    if type(p["timestamp"]) is not int or abs(int(time.time()) - p["timestamp"]) > 120:
        raise ValueError("stale candidate")
    if p["source"] != "verified_85_score_engine":
        raise ValueError("invalid source label")
    # This is only schema validation, not cryptographic source authentication.
    return sid

def process(body, *, db=DB, key=None):
    if key is None:
        key = load_key()
    unsigned = verify(body, secret=key)
    sid = validate(unsigned)
    with sqlite3.connect(db, timeout=20) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS sandbox_received ("
                     "research_signal_id TEXT PRIMARY KEY, received_at INTEGER NOT NULL, "
                     "payload TEXT NOT NULL)")
        result = conn.execute("INSERT OR IGNORE INTO sandbox_received VALUES (?,?,?)",
                              (sid, int(time.time()), json.dumps(body, sort_keys=True)))
        return "stored" if result.rowcount else "duplicate"

def poll_once(*, sqs=None, db=DB):
    if os.environ.get("SIGNALPILOT_SANDBOX_CONSUME_ENABLED") != "1":
        raise RuntimeError("sandbox consumer disabled")
    key = load_key()  # Fail closed before receiving any queue messages.
    sqs = sqs or boto3.client("sqs", region_name="il-central-1")
    response = sqs.receive_message(QueueUrl=QUEUE, MaxNumberOfMessages=5,
                                   WaitTimeSeconds=10, VisibilityTimeout=60)
    results = {"stored": 0, "duplicate": 0, "rejected": 0}
    for message in response.get("Messages", []):
        try:
            body = json.loads(message["Body"])
            outcome = process(body, db=db, key=key)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            # Do not delete invalid messages; retain for investigation / redrive.
            print(json.dumps({"rejected_message_id":message.get("MessageId"),
                              "reason":str(exc)}))
            results["rejected"] += 1
            continue
        sqs.delete_message(QueueUrl=QUEUE, ReceiptHandle=message["ReceiptHandle"])
        results[outcome] += 1
    return results

if __name__ == "__main__":
    print(json.dumps(poll_once(), sort_keys=True))
