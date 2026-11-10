"""Offline integrity audit of V2 historical OHLCV files and manifest.

Usage: python -m signals_v2.audit_history research_data/v2
Read-only; no network, credentials or orders.
"""
import argparse
import hashlib
import json
from pathlib import Path

STEPS = {"1m": 60_000, "5m": 300_000}
SYMBOLS = ("SOLUSDT", "XRPUSDT")


def validate_rows(rows, step, start, end):
    if not isinstance(rows, list) or len(rows) != (end - start) // step:
        raise ValueError("incomplete_coverage")
    for index, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != 6 or type(row[0]) is not int:
            raise ValueError("invalid_row")
        if row[0] != start + index * step:
            raise ValueError("missing_duplicate_or_misaligned")
        try:
            op, hi, lo, cl, vol = map(float, row[1:])
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("invalid_ohlcv") from exc
        from math import isfinite
        if not all(map(isfinite, (op, hi, lo, cl, vol))):
            raise ValueError("nonfinite_ohlcv")
        if lo <= 0 or vol < 0 or not lo <= min(op, cl) <= max(op, cl) <= hi:
            raise ValueError("invalid_ohlcv")


def audit(root):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text())
    from signals_v2.download_history import utc_ms
    start, end = utc_ms(manifest["start_utc"]), utc_ms(manifest["end_utc_exclusive"])
    datasets = {}
    entries = manifest["datasets"]
    if len(entries) != 4:
        raise ValueError("expected_four_datasets")
    for entry in entries:
        symbol, interval = entry["symbol"], entry["interval"]
        key = (symbol, interval)
        if symbol not in SYMBOLS or interval not in STEPS or key in datasets:
            raise ValueError("unexpected_or_duplicate_dataset")
        expected_name = f'{symbol}_{interval}_{manifest["start_utc"]}_{manifest["end_utc_exclusive"]}.json'
        if entry["file"] != expected_name:
            raise ValueError("unexpected_filename")
        payload = (root / expected_name).read_bytes()
        if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            raise ValueError("sha256_mismatch")
        rows = json.loads(payload)
        validate_rows(rows, STEPS[interval], start, end)
        if entry["rows"] != len(rows) or entry["first_open_ms"] != rows[0][0] or entry["last_open_ms"] != rows[-1][0]:
            raise ValueError("manifest_mismatch")
        datasets[key] = rows
    for symbol in SYMBOLS:
        minute = datasets[symbol, "1m"]
        five = datasets[symbol, "5m"]
        if len(minute) != len(five) * 5:
            raise ValueError("timeframe_count_mismatch")
        for i, row in enumerate(five):
            subset = minute[i * 5:(i + 1) * 5]
            expected = (float(subset[0][1]), max(float(x[2]) for x in subset),
                        min(float(x[3]) for x in subset), float(subset[-1][4]),
                        sum(float(x[5]) for x in subset))
            actual = tuple(map(float, row[1:]))
            if any(abs(a - b) > max(1e-8, abs(a) * 1e-6) for a, b in zip(actual, expected)):
                raise ValueError(f"cross_timeframe_mismatch_{symbol}_{row[0]}")
    return {"status": "OHLCV_INTEGRITY_PASS_ONLY", "start_ms": start,
            "end_ms_exclusive": end, "datasets": len(datasets),
            "symbols": list(SYMBOLS), "funding_verified": False,
            "oos_validated": False, "profitability_proven": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    args = parser.parse_args()
    print(json.dumps(audit(args.directory), sort_keys=True))


if __name__ == "__main__":
    main()
