"""Read-only offline CSV adapter for historical funding and order-book coverage.

Input files are local. This script never connects to an exchange or cloud
account. CSV columns are explicit; source authenticity remains unverified.
"""
import argparse
import csv
from pathlib import Path

from signals_v3.historical_market_coverage_report import audit_historical_market_coverage
from signals_v3.historical_coverage_gaps import historical_coverage_report_json


def read_csv_rows(path, required_columns):
    path = Path(path)
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("invalid_csv_columns")
        if not set(required_columns).issubset(reader.fieldnames):
            raise ValueError("missing_csv_columns")
        rows = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("invalid_csv_row")
            rows.append({key: row[key] for key in required_columns})
        return rows


def read_times(path):
    rows = read_csv_rows(path, ("timestamp_ms",))
    times = []
    for row in rows:
        raw = row["timestamp_ms"]
        if not raw.isascii() or not raw.isdecimal():
            raise ValueError("invalid_schedule_timestamp")
        times.append(int(raw))
    return times


def load_funding(path):
    rows = read_csv_rows(path, ("symbol", "funding_time_ms", "funding_rate"))
    for row in rows:
        raw = row["funding_time_ms"]
        if not raw.isascii() or not raw.isdecimal():
            raise ValueError("invalid_funding_timestamp")
        row["funding_time_ms"] = int(raw)
    return rows


def load_orderbook(path):
    fields = ("symbol", "timestamp_ms", "spread_bps",
              "bid_depth_10bps_usd", "ask_depth_10bps_usd")
    rows = read_csv_rows(path, fields)
    for row in rows:
        raw = row["timestamp_ms"]
        if not raw.isascii() or not raw.isdecimal():
            raise ValueError("invalid_orderbook_timestamp")
        row["timestamp_ms"] = int(raw)
    return rows


def run(funding_csv, funding_schedule_csv, orderbook_csv, decision_schedule_csv,
        symbol, max_orderbook_age_ms):
    report = audit_historical_market_coverage(
        load_funding(funding_csv), read_times(funding_schedule_csv),
        load_orderbook(orderbook_csv), read_times(decision_schedule_csv),
        symbol, max_orderbook_age_ms,
    )
    return historical_coverage_report_json(report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--funding-csv", required=True)
    parser.add_argument("--funding-schedule-csv", required=True)
    parser.add_argument("--orderbook-csv", required=True)
    parser.add_argument("--decision-schedule-csv", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--max-orderbook-age-ms", required=True, type=int)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run(args.funding_csv, args.funding_schedule_csv,
                 args.orderbook_csv, args.decision_schedule_csv,
                 args.symbol, args.max_orderbook_age_ms)
    output = Path(args.output)
    if output.exists():
        raise FileExistsError("refusing_to_overwrite_existing_report")
    output.write_text(result + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
