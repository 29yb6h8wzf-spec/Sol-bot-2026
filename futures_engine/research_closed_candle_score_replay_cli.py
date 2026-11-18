"""Offline closed-candle replay CLI for preexisting local SOL/XRP OHLCV JSON.

Input: {"SOL/USDT:USDT":{"5m":[[ms,o,h,l,c,v],...],"4h":[...]},
        "XRP/USDT:USDT":{"5m":[...],"4h":[...]}}
This is a research report, NOT a trade backtest or profitability estimate.
No network, exchange API, order placement, or live service changes.
"""
import argparse
import json
from pathlib import Path

from futures_engine.research_closed_candle_score_replay import replay_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Local preexisting OHLCV JSON")
    parser.add_argument("--output", required=True, help="New JSON report (refuses overwrite)")
    args = parser.parse_args(argv)
    source = Path(args.input).resolve(strict=True)
    dest = Path(args.output).resolve()
    if source == dest:
        parser.error("input_and_output_must_differ")
    with source.open(encoding="utf-8") as handle:
        datasets = json.load(handle)
    report = replay_report(datasets)
    with dest.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({"scans": report["totals"]["scans"],
                      "setups": report["totals"]["setups"],
                      "research_only": True, "execution_authorized": False}))


if __name__ == "__main__":
    main()
