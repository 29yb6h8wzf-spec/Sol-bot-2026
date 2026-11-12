"""Read-only historical Binance USD-M kline downloader for offline V2 research.

Usage: python -m signals_v2.download_history --start 2026-10-01 --end 2026-10-08 --output research_data/v2
Dates are UTC, end exclusive. No credentials, orders or production endpoints.
Never interpret successful downloads as evidence of profitability.
"""
import argparse
import hashlib
import json
import pathlib
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HOST = "https://fapi.binance.com/fapi/v1/klines"
INTERVALS = {"1m": 60_000, "5m": 300_000}
SYMBOLS = ("SOLUSDT", "XRPUSDT")


def utc_ms(value):
    dt = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def download(symbol, interval, start_ms, end_ms, *, fetch=None):
    if symbol not in SYMBOLS or interval not in INTERVALS:
        raise ValueError("unsupported_market")
    step = INTERVALS[interval]
    if start_ms >= end_ms or start_ms % step or end_ms % step:
        raise ValueError("invalid_utc_range")
    if fetch is None:
        def fetch(url):
            with urlopen(Request(url, headers={"User-Agent": "SignalPilot-V2-research"}),
                         timeout=30) as response:
                if response.status != 200:
                    raise RuntimeError("http_failure")
                return json.load(response)
    rows = []
    cursor = start_ms
    while cursor < end_ms:
        url = HOST + "?" + urlencode({"symbol": symbol, "interval": interval,
                                       "startTime": cursor, "endTime": end_ms - 1,
                                       "limit": 1500})
        batch = fetch(url)
        if not isinstance(batch, list) or not batch:
            raise ValueError(f"missing_history_at_{cursor}")
        for row in batch:
            if not isinstance(row, list) or len(row) < 6:
                raise ValueError("invalid_row")
            t = row[0]
            if type(t) is not int or t != cursor:
                raise ValueError(f"gap_duplicate_or_unsorted_at_{cursor}")
            prices = [float(x) for x in row[1:6]]
            if not (prices[2] <= min(prices[0], prices[3]) <=
                    max(prices[0], prices[3]) <= prices[1]) or prices[4] < 0:
                raise ValueError(f"invalid_ohlcv_at_{cursor}")
            if cursor >= end_ms:
                raise ValueError("outside_requested_range")
            rows.append(row[:6])
            cursor += step
            if cursor >= end_ms:
                break
        if len(batch) < 1500 and cursor < end_ms:
            raise ValueError(f"short_history_at_{cursor}")
    if len(rows) != (end_ms - start_ms) // step:
        raise ValueError("coverage_count_mismatch")
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", default="research_data/v2")
    args = parser.parse_args()
    start_ms, end_ms = utc_ms(args.start), utc_ms(args.end)
    if end_ms > int(time.time() * 1000) - 300_000:
        raise SystemExit("end_must_be_in_past")
    root = pathlib.Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    manifest = {"source": HOST, "start_utc": args.start, "end_utc_exclusive": args.end,
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "status": "DATA_ONLY_NOT_OOS", "datasets": []}
    for symbol in SYMBOLS:
        for interval in INTERVALS:
            rows = download(symbol, interval, start_ms, end_ms)
            payload = (json.dumps(rows, separators=(",", ":")) + "\n").encode()
            name = f"{symbol}_{interval}_{args.start}_{args.end}.json"
            (root / name).write_bytes(payload)
            manifest["datasets"].append({
                "symbol": symbol, "interval": interval, "file": name,
                "rows": len(rows), "first_open_ms": rows[0][0],
                "last_open_ms": rows[-1][0],
                "sha256": hashlib.sha256(payload).hexdigest(), "missing_bars": 0})
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
