"""One-shot SignalPilot executor. Run under a systemd oneshot with a persistent journal."""
import fcntl
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from decimal import Decimal as D
from pathlib import Path

from binance_permissions import credentials
from futures_engine.breakout_execution import route_breakout
from futures_engine.live import create_binance_client
from signals_v3.breakout_scan import latest_decision, scan


class Journal:
    def __init__(self, db):
        self.db = db
        db.execute("CREATE TABLE IF NOT EXISTS entries (id TEXT PRIMARY KEY, state TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS days (day TEXT PRIMARY KEY, equity TEXT NOT NULL)")
        db.commit()

    def claim(self, signal_id):
        with self.db:
            return self.db.execute("INSERT OR IGNORE INTO entries VALUES (?, 'CLAIMED')",
                                   (signal_id,)).rowcount == 1

    def mark(self, signal_id, state):
        with self.db:
            self.db.execute("UPDATE entries SET state=? WHERE id=?", (state, signal_id))

    def day_start(self, day, equity):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO days VALUES (?,?)", (day, str(equity)))
        return D(self.db.execute("SELECT equity FROM days WHERE day=?", (day,)).fetchone()[0])


def check_protection(exchange, journal, row, positions, now):
    signal_id, state = row
    if state != "PROTECTED":
        return "halt_unresolved_execution"
    _, raw_symbol, ts = signal_id.split("-")
    pair = raw_symbol[:-4] + "/USDT:USDT"
    amount = positions.get(raw_symbol, D(0))
    orders = exchange.fapiPrivateGetOpenAlgoOrders({"symbol": raw_symbol})
    orders = orders["orders"] if isinstance(orders, dict) else orders
    ours = {o["clientAlgoId"]: o for o in orders
            if o.get("clientAlgoId") in (signal_id+"-SL", signal_id+"-TP")}
    if amount:
        if len(ours) != 2 or now >= int(ts) + 4 * 3600_000:
            journal.mark(signal_id, "CLOSING")
            exchange.create_order(pair, "market", "sell" if amount > 0 else "buy",
                                  float(abs(amount)), None, {"reduceOnly": True,
                                  "newClientOrderId": signal_id+"-X"})
            if any(D(str(p["contracts"])) for p in exchange.fetch_positions([pair])):
                return "halt_close_unconfirmed"
        else:
            return "holding_protected_position"
    for order in ours.values():
        exchange.fapiPrivateDeleteAlgoOrder({"algoId": order["algoId"]})
    journal.mark(signal_id, "CLOSED")
    return "closed"


def tick(exchange, journal):
    now = int(exchange.fetch_time())
    if abs(now-time.time_ns()//1_000_000) > 5000:
        raise ValueError("clock_disagreement")
    decision = latest_decision(now)
    snapshot = exchange.fapiPrivateV3GetAccount()
    equity = D(snapshot["totalMarginBalance"])
    day = datetime.fromtimestamp(now/1000, timezone.utc).date().isoformat()
    baseline = journal.day_start(day, equity)
    positions = {p["symbol"]: D(p["positionAmt"]) for p in snapshot["positions"] if D(p["positionAmt"])}
    pending = journal.db.execute("SELECT id,state FROM entries WHERE state NOT IN ('CLOSED','RECOVERY_VERIFIED_FLAT')").fetchall()
    for row in pending:
        status = check_protection(exchange, journal, row, positions, now)
        if status != "closed":
            return status
    if positions or D(snapshot["totalOpenOrderInitialMargin"]) or D(snapshot["totalInitialMargin"]):
        return "existing_exposure"
    if decision is None or not 0 <= now-decision < 60_000:
        return "waiting_for_decision"
    if equity <= 0 or baseline-equity >= min(D("7.50"), baseline*D(".05")):
        return "risk_limit"
    for symbol in ("SOLUSDT","XRPUSDT"):
        if scan(symbol, decision)["status"] != "research_candidate":
            continue
        if journal.db.execute("SELECT 1 FROM entries WHERE id=?", (f"vb-{symbol}-{decision}",)).fetchone():
            continue
        available = D(snapshot["availableBalance"])
        if available < min(D("150"), equity)/2:
            return "insufficient_free_margin"
        exchange.load_markets()
        fee = D(exchange.fapiPrivateGetCommissionRate({"symbol":symbol})["takerCommissionRate"])
        result = route_breakout(exchange, symbol, decision, journal=journal,
                                account={"equity":equity, "day_start_equity":baseline,
                                         "fee_rate":max(fee,D(".0006"))})
        if "entry" in result:
            print(json.dumps({"symbol":symbol, "entry_id":result["entry"]["id"],
                              "stop_id":result["stop"]["algoId"], "target_id":result["target"]["algoId"]}))
            return "protected"
    return "no_candidate"


def main():
    root = Path(os.environ["STATE_DIRECTORY"])
    with (root/"runner.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        db = sqlite3.connect(root/"state.sqlite")
        try:
            exchange = create_binance_client(*credentials())
            exchange.options["adjustForTimeDifference"] = True
            print(json.dumps({"status":tick(exchange, Journal(db))}))
        finally:
            db.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"status":"blocked", "error_type": type(error).__name__}))
        raise SystemExit(1)
