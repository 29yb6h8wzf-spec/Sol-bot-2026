"""Offline diagnostics for score thresholds; NEVER changes the 85-point gate.

Scores are heuristic setup ranks, not success probabilities or live orders.
Only closed candles from a previously captured authorized market snapshot.
"""
import argparse
import json
from pathlib import Path

from futures_engine.verified_strategy_scan import to_strategy_candles
from strategies import candidates

THRESHOLDS = (70, 75, 80, 85)


def diagnose_snapshot(payload):
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported snapshot schema")
    observed = payload.get("captured_at_ms")
    if type(observed) is not int:
        raise ValueError("invalid snapshot capture time")
    reports = []
    seen = set()
    for item in payload.get("items", []):
        symbol = item["symbol"]
        if symbol not in ("SOL/USDT:USDT", "XRP/USDT:USDT") or symbol in seen:
            raise ValueError("unsupported or duplicate symbol")
        seen.add(symbol)
        five, four = item["five"], item["four"]
        for bars, duration in ((five, 300000), (four, 14400000)):
            if (len(bars) < 100
                    or any(type(b[0]) is not int for b in bars)
                    or any(b[0] + duration > observed for b in bars)
                    or any(b[0] + duration != a[0]
                           for b, a in zip(bars, bars[1:]))):
                raise ValueError("stale, unclosed, or noncontiguous market candles")
        if not five[-1][0] + 300000 <= observed < five[-1][0] + 600000:
            raise ValueError("snapshot outside forward signal window")
        setups, indicators = candidates(
            to_strategy_candles(five), to_strategy_candles(four),
        )
        reports.append({
            "symbol": symbol, "signal_candle_ms": five[-1][0],
            "indicators": indicators,
            "max_setup_score": max((s["score"] for s in setups), default=None),
            "raw_setup_count": len(setups),
            "counts_by_threshold": {
                str(t): sum(s["score"] >= t for s in setups)
                for t in THRESHOLDS
            },
            "raw_setups": [
                {"strategy": s["strategy"], "direction": s["direction"],
                 "score": s["score"], "reason": s["reason"]}
                for s in setups
            ],
            "execution_authorized": False,
        })
    if seen != {"SOL/USDT:USDT", "XRP/USDT:USDT"}:
        raise ValueError("both monitored symbols required")
    return {"status": "OFFLINE_DIAGNOSTICS_ONLY", "orders_sent": False,
            "captured_at_ms": observed, "reports": reports}


def main():
    parser = argparse.ArgumentParser(description="Offline setup-score diagnostics")
    parser.add_argument("--market-data-file", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(diagnose_snapshot(
        json.loads(args.market_data_file.read_text(encoding="utf-8"))
    ), sort_keys=True))


if __name__ == "__main__":
    main()
