"""Offline replay from scanner output and actual saved closed 5m candles.

The scanner signal is not synthesized. If there is no verified candidate, fail.
No network, exchange access, or production writes.
"""
import argparse
import json
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

from research.paper_independent_verifier import verify_saved_scan
from research.paper_risk_plan import replay_sized_candidate


def replay_saved_scan(scan, candles, *, database_path, candidate_index=0,
                      five_history=None, four_history=None,
                      entry_open_ms=None):
    if five_history is None or four_history is None:
        raise ValueError("independent 5m and 4h history required")
    verify_saved_scan(
        scan, five_history, four_history, candidate_index=candidate_index
    )
    if not isinstance(candles, list) or len(candles) < 2:
        raise ValueError("need signal candle and future closed candles")
    signal_ms = scan.get("closed_5m_candle_ms")
    signal = [b for b in candles if b.get("open_ms") == signal_ms]
    if len(signal) != 1 or signal[0].get("confirmed_closed") is not True:
        raise ValueError("missing unique confirmed signal candle")
    signal_close = Decimal(str(signal[0].get("close")))
    if not signal_close.is_finite() or signal_close <= 0:
        raise ValueError("invalid signal close")
    future = [b for b in candles if b.get("open_ms", -1) >= signal_ms + 300000]
    if not future:
        raise ValueError("no future candles")
    # Never silently ignore a missing or malformed candle between signal and
    # replay: the first replay candle must immediately follow the signal.
    if future[0]["open_ms"] != signal_ms + 300000:
        raise ValueError("gap after signal candle")
    # Keep the entire future series contiguous, even if entry is delayed.
    if entry_open_ms is None:
        entry_open_ms = signal_ms + 300000
    if (type(entry_open_ms) is not int or entry_open_ms < signal_ms + 300000
            or entry_open_ms % 300000):
        raise ValueError("invalid entry candle timestamp")
    entry_bars = [b for b in future if b["open_ms"] >= entry_open_ms]
    if not entry_bars or entry_bars[0]["open_ms"] != entry_open_ms:
        raise ValueError("entry candle not yet closed or missing")
    # The entry is the OPEN of the first eligible candle after capture.
    # Using the signal CLOSE assumes an unavailable fill and hides price gaps.
    first = entry_bars[0]
    if first.get("confirmed_closed") is not True:
        raise ValueError("entry candle must be confirmed closed")
    if "open" not in first:
        raise ValueError("next candle open required for honest paper fill")
    next_open = Decimal(str(first["open"]))
    low, high = Decimal(str(first["low"])), Decimal(str(first["high"]))
    if (not next_open.is_finite() or not low.is_finite()
            or not high.is_finite() or not 0 < low <= next_open <= high):
        raise ValueError("invalid next candle open")
    # A large gap is a missed fill, not permission to chase the market.
    if abs(next_open / signal_close - 1) > Decimal("0.005"):
        raise ValueError("entry gap exceeds 0.5 percent; skip paper entry")
    for previous, current in pairwise(future):
        if current["open_ms"] != previous["open_ms"] + 300000:
            raise ValueError("gap in future candle series")
    return replay_sized_candidate(
        scan, signal_close=signal_close, entry_mid=next_open,
        future_bars=entry_bars,
        database_path=database_path, candidate_index=candidate_index,
        entry_open_ms=entry_open_ms,
    )


def main():
    parser = argparse.ArgumentParser(description="Offline scan + closed 5m candle paper replay")
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--candles", type=Path, required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--five-history", type=Path, required=True)
    parser.add_argument("--four-history", type=Path, required=True)
    parser.add_argument("--candidate-index", type=int, default=0)
    args = parser.parse_args()
    result = replay_saved_scan(
        json.loads(args.scan.read_text(encoding="utf-8")),
        json.loads(args.candles.read_text(encoding="utf-8")),
        database_path=args.db, candidate_index=args.candidate_index,
        five_history=json.loads(args.five_history.read_text(encoding="utf-8")),
        four_history=json.loads(args.four_history.read_text(encoding="utf-8")),
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
