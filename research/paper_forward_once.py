"""One-shot, public-market-only forward Paper monitor for an isolated workspace.

Run from an external 5-minute scheduler after explicit deployment approval.
No credentials, exchange orders, SQS, production state, or background daemon.
"""
import argparse
import json
import time
from pathlib import Path

from futures_engine.market import closed_futures_bars
from research.paper_forward_capture import capture_scan
from research.paper_forward_followup import replay_captured_bundle

SYMBOLS = ("SOL/USDT:USDT", "XRP/USDT:USDT")


def _load_closed(loader, symbol):
    exchange, _market, rows = loader(symbol, "5m")
    try:
        return rows
    finally:
        if hasattr(exchange, "close"):
            exchange.close()


def process_pending(*, snapshot_dir, database_path, loader=None, now_ms=None):
    """Replay only signals previously captured before the next bar closed."""
    loader = closed_futures_bars if loader is None else loader
    observed = int(time.time() * 1000) if now_ms is None else int(now_ms)
    results = []
    for path in sorted(Path(snapshot_dir).glob("*.json")):
        try:
            bundle = json.loads(path.read_text(encoding="utf-8"))
            scan = bundle["scan"]
            signal_ms = scan["closed_5m_candle_ms"]
            captured = bundle.get("captured_at_ms")
            if (type(captured) is not int
                    or not signal_ms + 300000 <= captured < signal_ms + 600000):
                raise ValueError("missing valid forward capture timestamp")
            if not scan["candidates_85_plus"]:
                results.append({"snapshot": path.name, "status": "NO_SIGNAL"})
                continue
            entry_open_ms = (signal_ms + 300000 if captured == signal_ms + 300000
                             else signal_ms + 600000)
            if observed < entry_open_ms + 300000:
                results.append({"snapshot": path.name, "status": "WAITING_NEXT_BAR"})
                continue
            rows = _load_closed(loader, bundle["symbol"])
            future = [row for row in rows
                      if row[0] >= signal_ms + 300000
                      and row[0] + 300000 <= observed]
            if not future:
                results.append({"snapshot": path.name, "status": "WAITING_DATA"})
                continue
            for index in range(len(scan["candidates_85_plus"])):
                result = replay_captured_bundle(
                    bundle, future, database_path=database_path,
                    observed_at_ms=observed, candidate_index=index,
                )
                trade = result["result"]["trade"]
                results.append({
                    "snapshot": path.name, "candidate_index": index,
                    "status": trade["status"], "net_pnl": trade["net_pnl"],
                    "paper_only": True,
                })
        except Exception as exc:  # noqa: BLE001 - isolate failed public feeds
            results.append({
                "snapshot": path.name, "status": "BLOCKED",
                "reason": f"{type(exc).__name__}: {exc}",
            })
    return results


def run_once(*, snapshot_dir, database_path, symbols=SYMBOLS,
             loader=None, now_ms=None):
    loader = closed_futures_bars if loader is None else loader
    observed = int(time.time() * 1000) if now_ms is None else int(now_ms)
    captures = []
    for symbol in symbols:
        if symbol not in SYMBOLS:
            raise ValueError("unsupported monitoring symbol")
        try:
            captures.append(capture_scan(
                symbol, output_dir=snapshot_dir,
                loader=loader, now_ms=observed,
            ))
        except Exception as exc:  # noqa: BLE001 - isolate failed public feeds
            captures.append({
                "symbol": symbol, "status": "BLOCKED",
                "reason": f"{type(exc).__name__}: {exc}",
            })
    followups = process_pending(
        snapshot_dir=snapshot_dir, database_path=database_path,
        loader=loader, now_ms=observed,
    )
    return {
        "status": "RESEARCH_PAPER_ONLY", "captures": captures,
        "followups": followups, "orders_sent": False,
        "live_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser(description="One-shot read-only forward Paper monitor")
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--db", required=True)
    args = parser.parse_args()
    print(json.dumps(run_once(
        snapshot_dir=args.snapshot_dir, database_path=args.db,
    ), sort_keys=True))


if __name__ == "__main__":
    main()
