"""Offline research input from Binance's public daily market-data archives.

Only public OHLCV ZIPs; no trading API, credentials, or production writes.
Fails closed on missing days, duplicates, gaps, malformed candles.
"""
import argparse
import csv
import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen

from futures_engine.research_closed_candle_score_replay import _validate, FIVE_MS

NAMES = {"SOLUSDT": "SOL/USDT:USDT", "XRPUSDT": "XRP/USDT:USDT"}
BASE = "https://data.binance.vision/data/futures/um/daily/klines"


def archive_rows(symbol, day, *, opener=urlopen):
    if symbol not in NAMES:
        raise ValueError("unsupported_symbol")
    name = f"{symbol}-5m-{day}.zip"
    url = f"{BASE}/{symbol}/5m/{name}"
    with opener(url, timeout=30) as response:
        raw = response.read()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = [x for x in archive.namelist() if x.endswith(".csv")]
        if len(members) != 1:
            raise ValueError("invalid_archive_members")
        with archive.open(members[0]) as file:
            reader = csv.reader(io.TextIOWrapper(file, encoding="utf-8-sig"))
            rows = []
            for cells in reader:
                if cells and cells[0].lower() in ("open_time", "open time"):
                    continue
                if len(cells) < 6:
                    raise ValueError("invalid_archive_row")
                rows.append([int(cells[0]), *[float(v) for v in cells[1:6]]])
    return rows


def download(symbol, start_ms, cutoff_ms, *, opener=urlopen):
    if symbol not in NAMES:
        raise ValueError("unsupported_symbol")
    if (type(start_ms) is not int or type(cutoff_ms) is not int or
            start_ms < 0 or start_ms % FIVE_MS or
            cutoff_ms <= start_ms or cutoff_ms % FIVE_MS):
        raise ValueError("invalid_utc_range")
    start_day = datetime.fromtimestamp(start_ms / 1000, timezone.utc).date()
    end_day = datetime.fromtimestamp((cutoff_ms - 1) / 1000, timezone.utc).date()
    rows = []
    day = start_day
    while day <= end_day:
        rows.extend(archive_rows(symbol, day.isoformat(), opener=opener))
        day += timedelta(days=1)
    selected = [r for r in rows if start_ms <= r[0] and r[0] + FIVE_MS <= cutoff_ms]
    _validate(selected, FIVE_MS)
    if selected[0][0] != start_ms or selected[-1][0] + FIVE_MS != cutoff_ms:
        raise ValueError("incomplete_market_history")
    return selected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-ms", type=int, required=True)
    parser.add_argument("--cutoff-ms", type=int, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    data = {NAMES[s]: download(s, args.start_ms, args.cutoff_ms)
            for s in NAMES}
    with Path(args.output).open("x", encoding="utf-8") as file:
        json.dump(data, file, separators=(",", ":"))
        file.write("\n")
    print(json.dumps({"research_only": True,
                      "source": "data.binance.vision",
                      "rows": {s: len(v) for s, v in data.items()}}))


if __name__ == "__main__":
    main()
