"""Crash-safe local SQLite store for offline paper trades; no exchange access."""
import json
import sqlite3
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from research.paper_order_manager import PaperOrderManager, PaperTrade


class DurablePaperOrders:
    def __init__(self, path, taker_fee="0.0005", slippage="0.0002"):
        self.path = str(Path(path))
        self.fee, self.slippage = taker_fee, slippage
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS paper_trades (uid TEXT PRIMARY KEY, payload TEXT NOT NULL)")

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.execute("PRAGMA busy_timeout=10000")
        return db

    @staticmethod
    def _decode(raw):
        data = json.loads(raw)
        for field in ("quantity", "entry", "stop", "target", "exit_price", "gross_pnl", "net_pnl"):
            if data[field] is not None:
                data[field] = Decimal(data[field])
        return PaperTrade(**data)

    @staticmethod
    def _encode(trade):
        return json.dumps(asdict(trade), default=str, sort_keys=True)

    def get(self, uid):
        with self._connect() as db:
            row = db.execute("SELECT payload FROM paper_trades WHERE uid=?", (uid,)).fetchone()
        return self._decode(row[0]) if row else None

    def open(self, uid, side, quantity, mid, stop, target, timestamp, holding_seconds=1800):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute("SELECT payload FROM paper_trades WHERE uid=?", (uid,)).fetchone()
                if row:
                    trade = self._decode(row[0])
                else:
                    manager = PaperOrderManager(self.fee, self.slippage)
                    trade = manager.open(uid, side, quantity, mid, stop, target, timestamp, holding_seconds)
                    db.execute("INSERT INTO paper_trades(uid,payload) VALUES(?,?)",
                               (uid, self._encode(trade)))
                db.execute("COMMIT")
                return trade
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def update(self, uid, high, low, close, timestamp):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute("SELECT payload FROM paper_trades WHERE uid=?", (uid,)).fetchone()
                if not row:
                    raise KeyError(uid)
                manager = PaperOrderManager(self.fee, self.slippage)
                manager.trades[uid] = self._decode(row[0])
                trade = manager.update(uid, high, low, close, timestamp)
                db.execute("UPDATE paper_trades SET payload=? WHERE uid=?",
                           (self._encode(trade), uid))
                db.execute("COMMIT")
                return trade
            except BaseException:
                db.execute("ROLLBACK")
                raise
