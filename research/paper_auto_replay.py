"""Offline replay from scanner output and actual saved closed 5m candles.

The scanner signal is not synthesized. If there is no verified candidate, fail.
No network, exchange access, or production writes.
"""
import argparse
import json
from itertools import pairwise
from pathlib import Path

from research.paper_risk_plan import replay_sized_candidate


def replay_saved_scan(scan, candles, *, database_path, candidate_index=0):
    if not isinstance(candles, list) or len(candles) < 2:
        raise ValueError("need signal candle and future closed candles")
    signal_ms = scan.get("closed_5m_candle_ms")
    signal = [b for b in candles if b.get("open_ms") == signal_ms]
    if len(signal) != 1 or signal[0].get("confirmed_closed") is not True:
        raise ValueError("missing unique confirmed signal candle")
    signal_close = signal[0].get("close")
    future = [b for b in candles if b.get("open_ms", -1) >= signal_ms + 300000]
    if not future:
        raise ValueError("no future candles")
    # Never silently ignore a missing or malformed candle between signal and
    # replay: the first replay candle must immediately follow the signal.
    if future[0]["open_ms"] != signal_ms + 300000:
        raise ValueError("gap after signal candle")
    for previous, current in pairwise(future):
        if current["open_ms"] != previous["open_ms"] + 300000:
            raise ValueError("gap in future candle series")
    return replay_sized_candidate(
        scan, signal_close=signal_close, future_bars=future,
        database_path=database_path, candidate_index=candidate_index,
    )


def main():
    parser = argparse.ArgumentParser(description="Offline scan + closed 5m candle paper replay")
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--candles", type=Path, required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--candidate-index", type=int, default=0)
    args = parser.parse_args()
    result = replay_saved_scan(
        json.loads(args.scan.read_text(encoding="utf-8")),
        json.loads(args.candles.read_text(encoding="utf-8")),
        database_path=args.db, candidate_index=args.candidate_index,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
