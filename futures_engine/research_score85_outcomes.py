"""Research-only hypothetical 85+ signal outcomes; NOT execution or profitability proof.

Fixed predeclared assumptions: next 5m open entry, 1% stop, 2% target,
48 bars max hold, stop-first on same-bar ambiguity, 0.10% round-trip fees,
0.04% round-trip slippage. No funding or order-book modelling.
"""
import argparse
import json
from pathlib import Path

from futures_engine.research_aggregate_closed_4h import aggregate_closed_four_hour
from futures_engine.research_closed_candle_score_replay import replay_symbol, _validate, FIVE_MS

STOP_PCT = 0.01
TARGET_PCT = 0.02
MAX_HOLD = 48
COST_PCT = 0.0014
SYMBOLS = ("SOL/USDT:USDT", "XRP/USDT:USDT")


def evaluate_one(rows, signal_index, direction):
    entry_index = signal_index + 1
    if entry_index >= len(rows):
        return None
    entry = rows[entry_index][1]
    is_long = direction == "LONG"
    stop = entry * (1 - STOP_PCT if is_long else 1 + STOP_PCT)
    target = entry * (1 + TARGET_PCT if is_long else 1 - TARGET_PCT)
    last = min(entry_index + MAX_HOLD, len(rows))
    if last - entry_index < MAX_HOLD:
        return None
    for j in range(entry_index, last):
        high, low = rows[j][2], rows[j][3]
        stop_hit = low <= stop if is_long else high >= stop
        target_hit = high >= target if is_long else low <= target
        if stop_hit:
            exit_price, reason = stop, "stop_or_ambiguous"
        elif target_hit:
            exit_price, reason = target, "target"
        elif j == last - 1:
            exit_price, reason = rows[j][4], "time"
        else:
            continue
        gross = (exit_price / entry - 1) * (1 if is_long else -1)
        return {"entry_open_ms": rows[entry_index][0], "exit_open_ms": rows[j][0],
                "reason": reason, "gross_pct": round(gross * 100, 6),
                "net_pct": round((gross - COST_PCT) * 100, 6)}
    raise AssertionError("unreachable")


def evaluate(datasets):
    if not isinstance(datasets, dict) or set(datasets) != set(SYMBOLS):
        raise ValueError("require_both_symbols")
    events = []
    for symbol in SYMBOLS:
        rows = datasets[symbol]
        _validate(rows, FIVE_MS)
        four = aggregate_closed_four_hour(rows)
        scans = replay_symbol(symbol, rows, four, include_time=True)
        index = {r[0]: i for i, r in enumerate(rows)}
        for scan in scans:
            i = index[scan["closed_5m_open_ms"]]
            for setup in scan["setups"]:
                if setup["score"] < 85:
                    continue
                outcome = evaluate_one(rows, i, setup["direction"])
                if outcome is not None:
                    events.append({"symbol": symbol, "signal_open_ms": rows[i][0],
                                   **setup, **outcome})
    return {"research_only": True, "execution_authorized": False,
            "assumptions": {"entry": "next_5m_open", "stop_pct": 1,
                            "target_pct": 2, "max_hold_bars": 48,
                            "roundtrip_fee_pct": 0.10, "roundtrip_slippage_pct": 0.04,
                            "same_bar": "stop_first", "funding_included": False,
                            "overlap": "allowed; not independent trades"},
            "summary": {"events": len(events),
                        "net_positive": sum(e["net_pct"] > 0 for e in events),
                        "net_negative": sum(e["net_pct"] < 0 for e in events),
                        "mean_net_pct": (round(sum(e["net_pct"] for e in events) / len(events), 6)
                                         if events else None)},
            "events": events}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    with Path(args.input).open(encoding="utf-8") as file:
        result = evaluate(json.load(file))
    with Path(args.output).open("x", encoding="utf-8") as file:
        json.dump(result, file, sort_keys=True, indent=2)
        file.write("\n")
    print(json.dumps(result["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
