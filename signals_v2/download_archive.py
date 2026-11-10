"""Download official Binance public daily archive ZIPs, fail closed on gaps.

Usage: python -m signals_v2.download_archive --start 2026-11-02 --end 2026-11-09 --output research_data/v2
End UTC date exclusive. Data-only; no keys or orders.
"""
import argparse
import csv
import hashlib
import io
import json
import pathlib
import time
import zipfile
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from signals_v2.download_history import SYMBOLS, INTERVALS, utc_ms

BASE = "https://data.binance.vision/data/futures/um/daily/klines"


def fetch_archive(symbol, interval, day, *, opener=urlopen):
    if symbol not in SYMBOLS or interval not in INTERVALS:
        raise ValueError("unsupported_market")
    name = f"{symbol}-{interval}-{day}.zip"
    url = f"{BASE}/{symbol}/{interval}/{name}"
    with opener(Request(url, headers={"User-Agent": "SignalPilot-V2-research"}), timeout=45) as response:
        payload = response.read()
    if len(payload) > 50_000_000:
        raise ValueError("archive_too_large")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        if len(names) != 1 or not names[0].endswith(".csv") or "/" in names[0]:
            raise ValueError("unexpected_archive_members")
        with archive.open(names[0]) as stream:
            decoded = io.TextIOWrapper(stream, encoding="utf-8-sig")
            rows = []
            for row in csv.reader(decoded):
                if not row or row[0].lower() in ("open_time", "open time"):
                    continue
                if len(row) < 6:
                    raise ValueError("invalid_archive_row")
                rows.append([int(row[0]), *row[1:6]])
    return rows, {"url": url, "zip_sha256": hashlib.sha256(payload).hexdigest(),
                  "zip_bytes": len(payload)}


def collect(start, end, output, *, fetch=fetch_archive):
    start_ms, end_ms = utc_ms(start), utc_ms(end)
    if start_ms >= end_ms or end_ms > int(time.time() * 1000) - 300_000:
        raise ValueError("invalid_or_unclosed_range")
    root = pathlib.Path(output)
    root.mkdir(parents=True, exist_ok=True)
    manifest = {"source": BASE, "start_utc": start, "end_utc_exclusive": end,
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "status": "DATA_ONLY_NOT_OOS", "datasets": []}
    for symbol in SYMBOLS:
        for interval, step in INTERVALS.items():
            all_rows, archives = [], []
            day = datetime.strptime(start, "%Y-%m-%d").date()
            last = datetime.strptime(end, "%Y-%m-%d").date()
            while day < last:
                rows, meta = fetch(symbol, interval, day.isoformat())
                expected_start = utc_ms(day.isoformat())
                if len(rows) != 86_400_000 // step:
                    raise ValueError(f"incomplete_archive_{symbol}_{interval}_{day}")
                for i, row in enumerate(rows):
                    if row[0] != expected_start + i * step:
                        raise ValueError(f"gap_duplicate_or_misaligned_{symbol}_{interval}_{day}")
                all_rows.extend(rows)
                archives.append(meta)
                day += timedelta(days=1)
            payload = (json.dumps(all_rows, separators=(",", ":")) + "\n").encode()
            name = f"{symbol}_{interval}_{start}_{end}.json"
            (root / name).write_bytes(payload)
            manifest["datasets"].append({
                "symbol": symbol, "interval": interval, "file": name,
                "rows": len(all_rows), "first_open_ms": all_rows[0][0],
                "last_open_ms": all_rows[-1][0], "missing_bars": 0,
                "sha256": hashlib.sha256(payload).hexdigest(), "archives": archives})
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", default="research_data/v2")
    args = parser.parse_args()
    print(json.dumps(collect(args.start, args.end, args.output), indent=2))


if __name__ == "__main__":
    main()
