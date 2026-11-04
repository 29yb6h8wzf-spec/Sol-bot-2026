"""Opt-in end-to-end public archive -> replay -> hypothetical journal.

Downloads ONLY Binance Vision public klines, verifies checksum, reads ZIP
in memory, then records a hypothetical outcome. No authenticated APIs/orders.
"""
import csv
import io
from datetime import date as Date, datetime, timezone
from .public_archive_download import download_daily_public_archive
from .offline_binance_archive_verify import verify_binance_archive
from .offline_replay_pipeline import process_one

def run_public_daily_replay(*, plan, symbol, day, directory,
                            journal_path, today_utc=None):
    if not isinstance(plan, dict) or plan.get("symbol") not in (
        symbol, symbol.replace("USDT", "/USDT:USDT")):
        raise ValueError("plan_symbol_mismatch")
    archive_day = Date.fromisoformat(day)
    start_ms = int(datetime.combine(archive_day, datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = start_ms + 86400000
    signal_ms = plan.get('closed_5m_candle_ms')
    if type(signal_ms) is not int or not (start_ms <= signal_ms < end_ms):
        raise ValueError('signal_outside_archive_day')
    downloaded = download_daily_public_archive(
        symbol=symbol, day=day, directory=directory, today_utc=today_utc)
    verified = verify_binance_archive(
        downloaded["zip_path"], downloaded["checksum_path"],
        symbol=symbol, date=day)
    decoded = verified["csv_bytes"].decode("utf-8-sig")
    candles = []
    for row in csv.reader(io.StringIO(decoded)):
        if not row:
            continue
        if row[0].strip().lower() in ("open_time", "open time"):
            continue
        if len(row) < 5:
            raise ValueError("invalid_archive_csv")
        timestamp = int(row[0])
        if timestamp < 1_000_000_000_000 or timestamp > 9_999_999_999_999:
            raise ValueError("expected_millisecond_timestamp")
        if not (start_ms <= timestamp < end_ms):
            raise ValueError('candle_outside_archive_day')
        candles.append([timestamp, *row[1:5]])
    if not candles:
        raise ValueError("empty_archive_csv")
    signal_close = plan.get("closed_5m_candle_ms")
    if type(signal_close) is not int:
        raise ValueError("invalid_signal_time")
    # Only use candles from the first eligible post-signal candle onward.
    selected = [c for c in candles if c[0] >= signal_close]
    if not selected:
        raise ValueError("signal_not_in_archive")
    # A daily archive contains closed candles, but a trailing partial day
    # must never be accepted. The downloader disallows today/future dates.
    end = selected[-1][0] + 300000
    result = process_one(
        plan=plan,
        history={"exchange": "BINANCE", "market": "USDT_M_FUTURES",
                 "symbol": symbol, "interval": "5m",
                 "fetched_at_ms": end + 300000,
                 "closed_through_ms": end, "klines": selected},
        journal_path=journal_path)
    result["archive_sha256"] = verified["archive_sha256"]
    result["archive_checksum_matched"] = True
    result["archive_checksum_origin_independently_verified"] = False
    result["orders_sent"] = False
    return result
