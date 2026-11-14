"""Notify the configured owner about filled SignalPilot SOL/XRP position transitions."""
import fcntl
import hashlib
import hmac
import http.client
import json
import os
import sqlite3
import time
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from binance_permissions import credentials
from binance_telegram_bridge import NoRedirect, load_ssm_secret, sign_payload

SYMBOLS = ("SOLUSDT", "XRPUSDT")
RELAY = "https://sol-bot-2026.29yb6h8wzf.workers.dev/internal/binance-research"


def signed_get(path, params, key, secret):
    query = urlencode(dict(params, timestamp=time.time_ns() // 1000000, recvWindow=5000))
    sig = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    conn = http.client.HTTPSConnection("fapi.binance.com", timeout=10)
    try:
        conn.request("GET", path + "?" + query + "&signature=" + sig, headers={"X-MBX-APIKEY":key})
        resp = conn.getresponse()
        if resp.status != 200:
            raise RuntimeError("account_read_http_" + str(resp.status))
        return json.load(resp)
    finally:
        conn.close()


def notify(payload):
    stamp = int(time.time())
    raw, signature = sign_payload(dict(payload, timestamp=stamp, type="SIGNALPILOT_FILL_V1"),
                                  load_ssm_secret(), stamp)
    req = Request(RELAY, data=raw, method="POST", headers={"Content-Type":"application/json",
                  "X-Signalpilot-Timestamp":str(stamp), "X-Signalpilot-Signature":signature})
    with build_opener(NoRedirect()).open(req, timeout=10) as resp:
        ack = json.load(resp)
        if ack.get("status") != "delivered_owner_only" or ack.get("research_only") is not False:
            raise RuntimeError("telegram_delivery_unconfirmed")


def poll(db, symbol, get):
    state = db.execute("SELECT last_id,qty,owned FROM cursors WHERE symbol=?", (symbol,)).fetchone()
    if not state:
        # Start at today's actual position. Bracket the snapshot to avoid missing a concurrent fill.
        latest = lambda: get("/fapi/v1/userTrades", {"symbol":symbol,"limit":1})
        before = latest()
        pos = get("/fapi/v3/positionRisk", {"symbol":symbol})
        if before != latest():
            raise RuntimeError("baseline_changed_retry")
        if any(p["positionSide"] != "BOTH" for p in pos):
            raise RuntimeError("unsupported_hedge_mode")
        qty = sum((Decimal(p["positionAmt"]) for p in pos), Decimal(0))
        with db:
            db.execute("INSERT INTO cursors VALUES(?,?,?,0)", (symbol,before[-1]["id"] if before else -1,str(qty)))
        return
    last_id, qty, owned = state
    qty = Decimal(qty)
    while True:
        rows = get("/fapi/v1/userTrades", {"symbol":symbol,"fromId":last_id+1,"limit":1000})
        for row in sorted(rows,key=lambda r:r["id"]):
            if row["id"] <= last_id:
                continue
            if row["positionSide"] != "BOTH" or row["symbol"] != symbol:
                raise RuntimeError("unexpected_position_mode")
            delta = Decimal(row["qty"]) * (1 if row["side"]=="BUY" else -1)
            new = qty + delta
            events = []
            if qty and qty*new <= 0:
                if owned:
                    events.append(("CLOSE",qty))
                owned = False
            if new and qty*new <= 0:
                order = get("/fapi/v1/order", {"symbol":symbol,"orderId":row["orderId"]})
                owned = order["clientOrderId"].startswith("vb-"+symbol+"-")
                if owned:
                    events.append(("OPEN",new))
            with db:
                for event, direction in events:
                    payload = dict(event=event, symbol=symbol, direction="LONG" if direction>0 else "SHORT",
                                   fill_ms=row["time"], order_id=str(row["orderId"]), price=row["price"])
                    db.execute("INSERT INTO notices VALUES(?,?,?,?,'pending')",
                               (symbol,row["id"],event,json.dumps(payload)))
                db.execute("UPDATE cursors SET last_id=?,qty=?,owned=? WHERE symbol=?",
                           (row["id"],str(new),owned,symbol))
            last_id, qty = row["id"], new
        if len(rows)<1000:
            return


def main():
    root = Path(os.environ["STATE_DIRECTORY"])
    with (root/"lock").open("a") as lock, sqlite3.connect(root/"events.sqlite") as db:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        db.execute("CREATE TABLE IF NOT EXISTS cursors(symbol TEXT PRIMARY KEY,last_id INTEGER,qty TEXT,owned INTEGER)")
        db.execute("CREATE TABLE IF NOT EXISTS notices(symbol TEXT,id INTEGER,event TEXT,payload TEXT,state TEXT,PRIMARY KEY(symbol,id,event))")
        key,secret = credentials()
        for sym in SYMBOLS:
            poll(db,sym,lambda path,params: signed_get(path,params,key,secret))
        for ident, raw in db.execute("SELECT rowid,payload FROM notices WHERE state='pending' ORDER BY rowid").fetchall():
            with db:
                db.execute("UPDATE notices SET state='sending' WHERE rowid=?", (ident,))
            notify(json.loads(raw))
            with db:
                db.execute("UPDATE notices SET state='delivered' WHERE rowid=?", (ident,))
        print("fill_monitor_ok symbols=2")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("fill_monitor_failed",type(exc).__name__, str(exc) if type(exc) is RuntimeError else "")
        raise SystemExit(1)
