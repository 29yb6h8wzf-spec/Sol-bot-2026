"""Offline replay from scanner output and actual saved closed 5m candles.

The scanner signal is not synthesized. If there is no verified candidate, fail.
Paper entry is the first post-signal candle OPEN; no signal-close fills.
No network, exchange access, or production writes.
"""
import argparse
import json
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from pathlib import Path

from research.paper_independent_verifier import verify_saved_scan
from research.paper_risk_plan import replay_sized_candidate


def replay_saved_scan(scan, candles, *, database_path, candidate_index=0,
                      five_history=None, four_history=None):
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
    future = [b for b in candles if b.get("open_ms", -1) >= signal_ms + 300000]
    if not future:
        raise ValueError("no future candles")
    # The simulated entry is the next 5m candle's OPEN, never the signal
    # candle's CLOSE. Validate the entire series before writing any trade.
    if future[0]["open_ms"] != signal_ms + 300000:
        raise ValueError("gap after signal candle")
    for previous, current in pairwise(future):
        if current["open_ms"] != previous["open_ms"] + 300000:
            raise ValueError("gap in future candle series")
    for bar in future:
        start = bar["open_ms"]
        if (bar.get("confirmed_closed") is not True
                or bar.get("close_ms") != start + 299999):
            raise ValueError("future candle must be a confirmed 5m bar")
        try:
            opening, high, low, closing = (
                Decimal(str(bar[field])) for field in ("open", "high", "low", "close")
            )
        except (KeyError, InvalidOperation, TypeError) as exc:
            raise ValueError("future candle must contain valid open/high/low/close") from exc
        if (not all(x.is_finite() and x > 0 for x in (opening, high, low, closing))
                or not low <= opening <= high
                or not low <= closing <= high):
            raise ValueError("future candle has invalid OHLC prices")
    entry_mid = Decimal(str(future[0]["open"]))
    return replay_sized_candidate(
        scan, entry_mid=entry_mid, future_bars=future,
        database_path=database_path, candidate_index=candidate_index,
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
