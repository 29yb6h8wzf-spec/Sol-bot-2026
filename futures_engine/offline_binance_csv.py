"""Offline Binance Futures public kline archive adapter.

Accepts a locally downloaded, manually supplied Binance public kline CSV.
No HTTP calls, credentials, SDKs, orders, or automatic trading.
A caller must independently verify the file's origin and integrity.
"""
import csv
from datetime import datetime, timezone
from pathlib import Path
from .offline_replay_pipeline import process_one

def load_public_klines(path, *, fetched_at_ms, closed_through_ms, max_rows=1500):
    if type(fetched_at_ms) is not int or type(closed_through_ms) is not int:
        raise ValueError("invalid_timestamps")
    if not 1 <= max_rows <= 1500:
        raise ValueError("invalid_max_rows")
    rows = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        for raw in reader:
            if not raw:
                continue
            if raw[0].strip().lower() in ("open_time", "open time"):
                continue
            if len(raw) < 5 or len(rows) >= max_rows:
                raise ValueError("invalid_csv_shape_or_size")
            # Binance historical kline CSV: open_time,open,high,low,close,...
            try:
                t = int(raw[0])
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid_open_time") from exc
            # Some public archives use microsecond timestamps. Explicitly
            # reject rather than silently misinterpret the candle time.
            if t < 1000000000000 or t > 9999999999999:
                raise ValueError("expected_millisecond_timestamp")
            rows.append([t, raw[1], raw[2], raw[3], raw[4]])
    if not rows:
        raise ValueError("empty_archive")
    return {"fetched_at_ms": fetched_at_ms,
            "closed_through_ms": closed_through_ms,
            "klines": rows}

def replay_from_local_csv(*, plan, csv_path, symbol, fetched_at_ms,
                          closed_through_ms, journal_path):
    if symbol not in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"):
        raise ValueError("unsupported_symbol")
    archive = load_public_klines(csv_path, fetched_at_ms=fetched_at_ms,
                                 closed_through_ms=closed_through_ms)
    history = dict(archive, exchange="BINANCE", market="USDT_M_FUTURES",
                   symbol=symbol, interval="5m")
    result = process_one(plan=plan, history=history, journal_path=journal_path)
    result["archive_authenticity_verified"] = False
    result["archive_origin"] = "USER_SUPPLIED_LOCAL_CSV_UNVERIFIED"
    return result
