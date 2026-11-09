"""Offline follow-up of an immutable scanner snapshot with later closed candles.

The snapshot must have been captured before future bars were available for
genuine forward evidence. This tool does not independently prove capture time.
No exchange access, trading keys, order placement, or production writes.
"""
import argparse
import json
import time
from pathlib import Path

from futures_engine.verified_strategy_scan import to_strategy_candles
from research.paper_auto_replay import replay_saved_scan


def replay_captured_bundle(bundle, future, *, database_path,
                           observed_at_ms=None, candidate_index=0):
    if (bundle.get("schema_version") != 1
            or bundle.get("symbol") != bundle.get("scan", {}).get("symbol")):
        raise ValueError("invalid immutable scan bundle")
    scan = bundle["scan"]
    five, four = bundle["five"], bundle["four"]
    signal_ms = scan["closed_5m_candle_ms"]
    if not isinstance(future, list) or not future:
        raise ValueError("future closed candles required")
    now = int(time.time() * 1000) if observed_at_ms is None else observed_at_ms
    previous = signal_ms
    paper_bars = [{
        "open_ms": five[-1][0], "close_ms": five[-1][0] + 299999,
        "open": five[-1][1], "high": five[-1][2],
        "low": five[-1][3], "close": five[-1][4],
        "confirmed_closed": True,
    }]
    for row in future:
        if not isinstance(row, list) or len(row) < 6:
            raise ValueError("invalid future OHLCV")
        opened = row[0]
        if (type(opened) is not int or opened != previous + 300000
                or opened + 300000 > now):
            raise ValueError("future bars not closed or contiguous")
        paper_bars.append({
            "open_ms": opened, "close_ms": opened + 299999,
            "open": row[1], "high": row[2], "low": row[3],
            "close": row[4], "confirmed_closed": True,
        })
        previous = opened
    if not scan.get("candidates_85_plus"):
        return {
            "status": "NO_VERIFIED_SIGNAL", "symbol": bundle["symbol"],
            "orders_sent": False, "paper_trade_opened": False,
        }
    result = replay_saved_scan(
        scan, paper_bars, database_path=database_path,
        candidate_index=candidate_index,
        five_history=to_strategy_candles(five),
        four_history=to_strategy_candles(four),
    )
    return {
        "status": "OFFLINE_PAPER_REPLAY", "symbol": bundle["symbol"],
        "signal_open_ms": signal_ms, "result": result,
        "orders_sent": False, "live_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Offline forward-snapshot paper follow-up")
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--future", required=True, type=Path)
    parser.add_argument("--db", required=True)
    args = parser.parse_args()
    result = replay_captured_bundle(
        json.loads(args.bundle.read_text(encoding="utf-8")),
        json.loads(args.future.read_text(encoding="utf-8")),
        database_path=args.db,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
