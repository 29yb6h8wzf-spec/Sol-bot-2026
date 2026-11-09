"""Historical rolling entry-filter audit with strict 4h close-time alignment.

Descriptive, in-sample research only: not a backtest, not out-of-sample,
not an execution engine, and not evidence of profitable trading.
"""
import argparse
import json
from bisect import bisect_right
from collections import Counter
from itertools import pairwise
from pathlib import Path

from futures_engine.verified_strategy_scan import to_strategy_candles
from research.paper_filter_audit import audit_filters
from strategies import candidates


def _validate(rows, duration):
    if not isinstance(rows, list) or len(rows) < 100:
        raise ValueError("insufficient closed history")
    for row in rows:
        if (not isinstance(row, list) or len(row) < 6
                or type(row[0]) is not int or row[0] < 0
                or row[0] % duration):
            raise ValueError("invalid candle history")
    if any(b[0] + duration != a[0] for b, a in pairwise(rows)):
        raise ValueError("noncontiguous candle history")


def rolling_filter_report(five, four, *, symbol, asof_ms):
    if symbol not in ("SOL/USDT:USDT", "XRP/USDT:USDT"):
        raise ValueError("unsupported research symbol")
    if type(asof_ms) is not int:
        raise ValueError("invalid observation timestamp")
    _validate(five, 300000)
    _validate(four, 14400000)
    if five[-1][0] + 300000 > asof_ms or four[-1][0] + 14400000 > asof_ms:
        raise ValueError("unclosed market candle")
    five_all = to_strategy_candles(five)
    four_all = to_strategy_candles(four)
    four_closed_at = [row[0] + 14400000 for row in four]
    counts = Counter()
    gate_passes = Counter()
    gate_total = Counter()
    scans = []
    for index in range(99, len(five)):
        closed_at = five[index][0] + 300000
        # Only use 4h bars closed when this 5m candle finished.
        n_four = bisect_right(four_closed_at, closed_at)
        if n_four < 100:
            continue
        history_five = five_all[:index + 1]
        history_four = four_all[:n_four]
        gates = audit_filters(history_five, history_four)
        setups, _ = candidates(history_five, history_four)
        eligible = [s for s in setups if s["score"] >= 85]
        counts["scans"] += 1
        counts["raw_setups"] += len(setups)
        counts["setups_85_plus"] += len(eligible)
        for row in gates:
            key = row["strategy"] + ":" + row["direction"]
            counts[key + ":all_pass"] += int(row["passed"])
            for gate in row["conditions"]:
                name = key + ":" + gate["name"]
                gate_total[name] += 1
                gate_passes[name] += int(gate["passed"])
        scans.append({
            "candle_ms": five[index][0],
            "four_hour_last_closed_ms": four[n_four - 1][0] + 14400000,
            "setups_85_plus": [
                {"strategy": s["strategy"], "direction": s["direction"],
                 "score": s["score"]} for s in eligible
            ],
        })
    return {
        "status": "HISTORICAL_IN_SAMPLE_FILTER_AUDIT",
        "symbol": symbol, "orders_sent": False,
        "profitable_claim": False, "out_of_sample": False,
        "first_scan_ms": scans[0]["candle_ms"] if scans else None,
        "last_scan_ms": scans[-1]["candle_ms"] if scans else None,
        "counts": dict(sorted(counts.items())),
        "filter_pass_rates": {
            key: {"passed": gate_passes[key], "total": total}
            for key, total in sorted(gate_total.items())
        },
        "scans": scans,
    }


def main():
    parser = argparse.ArgumentParser(description="Offline rolling strategy filter audit")
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if "items" in payload:
        reports = [rolling_filter_report(
            item["five"], item["four"], symbol=item["symbol"],
            asof_ms=payload["captured_at_ms"],
        ) for item in payload["items"]]
    else:
        reports = [rolling_filter_report(
            payload["five"], payload["four"], symbol=payload["symbol"],
            asof_ms=payload["asof_ms"],
        )]
    for report in reports:
        report.pop("scans")
        print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
