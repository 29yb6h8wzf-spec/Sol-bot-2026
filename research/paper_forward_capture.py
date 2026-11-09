"""Read-only forward research scanner snapshot capture.

One immutable JSON snapshot per symbol and closed 5m candle. No paper order,
exchange order, SQS, credentials, or deployment action is performed.
"""
import argparse
import json
import os
import tempfile
from pathlib import Path

from futures_engine.verified_strategy_scan import evaluate, to_strategy_candles
from research.paper_independent_verifier import verify_saved_scan


def capture_scan(symbol, *, output_dir, loader=None, now_ms=None):
    # Retain exactly the candles used by the scanner, not a later fetch.
    # A bare scan JSON is insufficient to independently verify its signal.
    observed = {}
    if loader is None:
        from futures_engine.market import closed_futures_bars
        loader = closed_futures_bars

    def capturing_loader(requested_symbol, timeframe):
        exchange, market, rows = loader(requested_symbol, timeframe)
        observed[timeframe] = rows
        return exchange, market, rows

    scan = evaluate(symbol, loader=capturing_loader, now_ms=now_ms)
    if (scan.get("status") != "RESEARCH_ONLY"
            or scan.get("orders_sent") is not False
            or scan.get("sqs_sent") is not False):
        raise ValueError("non-read-only scan refused")
    candle_ms = scan["closed_5m_candle_ms"]
    if type(candle_ms) is not int or candle_ms < 0 or candle_ms % 300000:
        raise ValueError("invalid closed 5m timestamp")
    five = observed.get("5m")
    four = observed.get("4h")
    if not isinstance(five, list) or not isinstance(four, list):
        raise TypeError("missing scanner candle history")
    for index in range(len(scan["candidates_85_plus"])):
        verify_saved_scan(
            scan, to_strategy_candles(five), to_strategy_candles(four),
            candidate_index=index,
        )
    # No future candles are stored in this immutable signal-time bundle.
    bundle = {
        "schema_version": 1, "symbol": symbol, "scan": scan,
        "five": five, "four": four,
    }
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    name = f"{symbol.replace('/USDT:USDT', 'USDT')}-{candle_ms}.json"
    destination = directory / name
    payload = json.dumps(bundle, sort_keys=True, separators=(",", ":"))
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=directory, delete=False
        ) as tmp:
            temp_path = Path(tmp.name)
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
        try:
            os.link(temp_path, destination)
            state = "RECORDED"
        except FileExistsError:
            if destination.read_text(encoding="utf-8") != payload:
                raise ValueError("conflicting existing candle snapshot")
            state = "ALREADY_RECORDED"
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return {
        "status": state, "symbol": symbol,
        "closed_5m_candle_ms": candle_ms,
        "candidate_count": len(scan["candidates_85_plus"]),
        "snapshot_path": str(destination),
        "history_candles_5m": len(five), "history_candles_4h": len(four),
        "orders_sent": False, "paper_trade_opened": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Read-only research scanner capture")
    parser.add_argument("--symbol", choices=("SOL/USDT:USDT", "XRP/USDT:USDT"),
                        required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(capture_scan(args.symbol, output_dir=args.output_dir),
                     sort_keys=True))


if __name__ == "__main__":
    main()
