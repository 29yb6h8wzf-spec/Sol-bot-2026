"""Offline score-band replay from a single 5m OHLCV JSON file.

Input: {"SOL/USDT:USDT": [[open_ms,o,h,l,c,v],...],
        "XRP/USDT:USDT": [[open_ms,o,h,l,c,v],...]}
The UTC-aligned closed 4h candles are derived from each 5m series.
This is a setup-count report, NOT a trading backtest.
"""
import argparse
import json
from pathlib import Path

from futures_engine.research_aggregate_closed_4h import aggregate_closed_four_hour
from futures_engine.research_closed_candle_score_replay import replay_report
from futures_engine.research_setup_score_distribution import ALLOWED_SYMBOLS


def report_from_five_minute(datasets):
    if not isinstance(datasets, dict) or not datasets or set(datasets) - ALLOWED_SYMBOLS:
        raise ValueError("invalid_symbols")
    prepared = {}
    for symbol, rows in datasets.items():
        four = aggregate_closed_four_hour(rows)
        if len(four) < 100:
            raise ValueError("insufficient_4h_history")
        prepared[symbol] = {"5m": rows, "4h": four}
    return replay_report(prepared)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    source = Path(args.input).resolve(strict=True)
    dest = Path(args.output).resolve()
    if source == dest:
        parser.error("input_and_output_must_differ")
    with source.open(encoding="utf-8") as f:
        report = report_from_five_minute(json.load(f))
    with dest.open("x", encoding="utf-8") as f:
        json.dump(report, f, sort_keys=True, indent=2)
        f.write("\n")
    print(json.dumps({"scans": report["totals"]["scans"],
                      "setups": report["totals"]["setups"],
                      "research_only": True,
                      "execution_authorized": False}))


if __name__ == "__main__":
    main()
