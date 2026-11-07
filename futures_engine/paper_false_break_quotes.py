"""Public Binance USD-M quote observations for the frozen 5m false-break rule.

Run manually with python -m futures_engine.paper_false_break_quotes --db research.sqlite
Use a dedicated local research database. Polls the latest boundary and never
reconstructs quotes from candles. Checkpoints are measured from signal-bar close.
"""
import argparse
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from decimal import Decimal
from http.client import HTTPException
from statistics import median
from urllib.parse import urlencode
from urllib.request import urlopen

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT")
STEP = 300_000
WINDOW = 15_000
MAX_QUOTE_AGE = 3_000


def now_ms():
    return time.time_ns() // 1_000_000


def public_get(endpoint, **params):
    url = "https://fapi.binance.com/fapi/v1/" + endpoint + "?" + urlencode(params)
    with urlopen(url, timeout=3) as response:
        return json.load(response)


def positive(value):
    number = Decimal(str(value))
    if not number.is_finite() or number <= 0:
        raise ValueError("invalid_positive_number")
    return number


def signal(rows, close_ms):
    """Require the exact 13 closed bars ending at this UTC boundary."""
    if len(rows) != 13:
        raise ValueError("missing_closed_history")
    bars = []
    for i, row in enumerate(rows):
        start = close_ms - (13 - i) * STEP
        if row[0] != start or row[6] != start + STEP - 1:
            raise ValueError("unexpected_bar_timestamp")
        op, high, low, close = map(positive, row[1:5])
        volume, quote, bought = (Decimal(str(row[j])) for j in (5, 7, 9))
        if (not all(v.is_finite() for v in (volume, quote, bought))
                or not 0 <= bought <= volume or quote < 0
                or not low <= min(op, close) <= max(op, close) <= high):
            raise ValueError("invalid_bar_values")
        bars.append((high, low, close, volume, quote, bought))
    high, low, close, volume, quote, bought = bars[-1]
    floor = min(b[1] for b in bars[:-1])
    ceiling = max(b[0] for b in bars[:-1])
    if volume == 0 or quote < Decimal("1.5") * median(b[4] for b in bars[:-1]):
        return None
    if low < floor and high > ceiling:
        return None
    if low < floor < close and bought <= Decimal("0.4") * volume:
        return "LONG"
    if high > ceiling > close and bought >= Decimal("0.6") * volume:
        return "SHORT"
    return None


def initialize(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS false_break_scans (
        symbol TEXT, close_ms INTEGER, side TEXT, detected_ms INTEGER,
        sweep_extreme TEXT, overlaps_prior_signal_window INTEGER,
        PRIMARY KEY(symbol, close_ms)
    );
    CREATE TABLE IF NOT EXISTS false_break_quotes (
        symbol TEXT, close_ms INTEGER, horizon_min INTEGER, due_ms INTEGER,
        status TEXT NOT NULL, requested_ms INTEGER, received_ms INTEGER,
        book_ms INTEGER, bid TEXT, ask TEXT, reason TEXT,
        PRIMARY KEY(symbol, close_ms, horizon_min)
    );
    CREATE INDEX IF NOT EXISTS false_break_due ON false_break_quotes(symbol,status,due_ms);
    """)


def observe(db, symbol, *, clock=now_ms, get=public_get):
    start = clock()
    boundary = start // STEP * STEP
    if start - boundary <= WINDOW and not db.execute(
        "SELECT 1 FROM false_break_scans WHERE symbol=? AND close_ms=?",
        (symbol, boundary)
    ).fetchone():
        try:
            rows = get("klines", symbol=symbol, interval="5m", endTime=boundary-1, limit=13)
            side = signal(rows, boundary)
        except (OSError, HTTPException, ValueError, KeyError, IndexError, TypeError, ArithmeticError) as exc:
            print(f"{symbol} kline scan failed: {type(exc).__name__}", flush=True)
        else:
            detected = clock()
            if boundary <= detected <= boundary + WINDOW:
                with db:
                    prior = db.execute("SELECT 1 FROM false_break_scans WHERE symbol=? "
                                       "AND side IS NOT NULL AND close_ms>? AND close_ms<? LIMIT 1",
                                       (symbol, boundary - 3*STEP, boundary)).fetchone()
                    extreme = str(rows[-1][3 if side == "LONG" else 2]) if side else None
                    inserted = db.execute("INSERT OR IGNORE INTO false_break_scans VALUES(?,?,?,?,?,?)",
                                          (symbol, boundary, side, detected, extreme, int(bool(prior))))
                    if inserted.rowcount and side:
                        db.executemany(
                            "INSERT OR IGNORE INTO false_break_quotes "
                            "(symbol,close_ms,horizon_min,due_ms,status) VALUES(?,?,?,?,'PENDING')",
                            [(symbol, boundary, m, boundary + 60_000*m) for m in (0, 5, 10, 15)]
                        )
    requested = clock()
    with db:
        db.execute("UPDATE false_break_quotes SET status='MISSING', reason='missed_window' "
                   "WHERE symbol=? AND status='PENDING' AND due_ms < ?",
                   (symbol, requested - WINDOW))
    # All signal boundaries and horizons are 5m-aligned. Multiple signals due
    # at the same boundary may share the same actual public book observation.
    pending = db.execute("SELECT DISTINCT due_ms FROM false_break_quotes "
                         "WHERE symbol=? AND status='PENDING' AND due_ms<=?",
                         (symbol, requested)).fetchall()
    for (due,) in pending:
        requested = clock()
        if not due <= requested <= due + WINDOW:
            continue
        stamp = bid = ask = None
        reason = None
        try:
            book = get("ticker/bookTicker", symbol=symbol)
            received = clock()
            if book["symbol"] != symbol or type(book["time"]) is not int:
                raise ValueError("invalid_book_identity")
            stamp = book["time"]
            bid, ask = positive(book["bidPrice"]), positive(book["askPrice"])
            if bid >= ask:
                raise ValueError("crossed_or_locked_book")
            if not requested <= received <= due + WINDOW:
                raise ValueError("late_or_reversed_clock")
            if not due <= stamp <= received or received - stamp > MAX_QUOTE_AGE:
                raise ValueError("stale_or_future_book")
        except (OSError, HTTPException, ValueError, KeyError, TypeError, ArithmeticError) as exc:
            received = clock()
            reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        with db:
            db.execute("UPDATE false_break_quotes SET status=?,requested_ms=?,received_ms=?,"
                       "book_ms=?,bid=?,ask=?,reason=? WHERE symbol=? AND due_ms=? AND status='PENDING'",
                       ("MISSING" if reason else "OBSERVED", requested, received, stamp,
                        None if reason else str(bid), None if reason else str(ask),
                        reason, symbol, due))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    with closing(sqlite3.connect(args.db)) as db:
        initialize(db)

    def run_symbol(symbol):
        with closing(sqlite3.connect(args.db, timeout=10)) as db:
            observe(db, symbol)

    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as workers:
        while True:
            list(workers.map(run_symbol, SYMBOLS))
            if args.once:
                return
            time.sleep(2)


if __name__ == "__main__":
    main()
