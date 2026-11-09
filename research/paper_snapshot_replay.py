"""Offline historical scanner-to-paper evidence from saved Binance klines.

No network access, broker clients, SQS, live trading, or future data in signal
formation. A historical replay is NOT a forward-tested or live trade.
"""
import argparse
import json
from pathlib import Path

from futures_engine.verified_strategy_scan import evaluate, to_strategy_candles
from research.paper_auto_replay import replay_saved_scan


class _OfflineExchange:
    def close(self):
        pass


def run_snapshot(snapshot, *, database_path):
    symbol = snapshot["symbol"]
    five = snapshot["five"]
    four = snapshot["four"]
    future = snapshot["future"]
    signal_ms = snapshot["signal_5m_open_ms"]
    asof_ms = snapshot["asof_ms"]
    if five[-1][0] != signal_ms or asof_ms < signal_ms + 300000:
        raise ValueError("signal timestamp does not match snapshot")
    if not future or future[0][0] != signal_ms + 300000:
        raise ValueError("future closed candles must immediately follow signal")

    def loader(requested_symbol, timeframe):
        if requested_symbol != symbol or timeframe not in ("5m", "4h"):
            raise ValueError("unexpected market request")
        return _OfflineExchange(), {}, five if timeframe == "5m" else four

    scan = evaluate(symbol, loader=loader, now_ms=asof_ms)
    if not scan["candidates_85_plus"]:
        return {
            "status": "NO_VERIFIED_SIGNAL", "symbol": symbol,
            "historical_replay": True, "orders_sent": False,
        }

    def paper_bar(row):
        return {
            "open_ms": row[0], "close_ms": row[0] + 299999,
            "open": row[1], "high": row[2], "low": row[3], "close": row[4],
            "confirmed_closed": True,
        }

    paper = replay_saved_scan(
        scan, [paper_bar(five[-1]), *(paper_bar(r) for r in future)],
        database_path=database_path, candidate_index=0,
        five_history=to_strategy_candles(five),
        four_history=to_strategy_candles(four),
    )
    candidate = scan["candidates_85_plus"][0]
    return {
        "status": "HISTORICAL_PAPER_REPLAY", "symbol": symbol,
        "signal_open_ms": signal_ms,
        "strategy": candidate["strategy"], "direction": candidate["direction"],
        "score": candidate["score"],
        "trade": paper["trade"], "risk_plan": paper["paper_plan"],
        "bars_processed": paper["bars_processed"],
        "historical_replay": True, "orders_sent": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Offline verified historical paper replay")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--db", required=True)
    args = parser.parse_args()
    snapshot = json.loads(args.input.read_text(encoding="utf-8"))
    print(json.dumps(run_snapshot(snapshot, database_path=args.db), sort_keys=True))


if __name__ == "__main__":
    main()
