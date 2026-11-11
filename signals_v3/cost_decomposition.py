"""Exploratory per-trade cost decomposition for V3 replay (research only).

Answers one question: are V3 losses caused by execution costs relative to a
tight stop, or by the signals themselves?  For every trade it splits net R into

    raw_r      price move from reference open to reference exit, in R (no costs)
    slippage_r adverse entry+exit slippage, in R
    fee_r      taker fees, in R
    funding_r  historical funding, in R

so that net_r == raw_r - slippage_r - fee_r - funding_r.

The 2024-11..2026-10 window has already been fully inspected, so nothing here is
out-of-sample evidence and no output may be used to certify an edge.
"""
import argparse
import json
from math import sqrt
from pathlib import Path
from statistics import mean, pstdev

SLIPPAGE_PER_SIDE = 0.0002
STOP_WIDTH_BUCKETS = (0.0025, 0.005, 0.01, 0.02)


def decompose(record, slippage_per_side=SLIPPAGE_PER_SIDE):
    side = 1 if record["direction"] == "LONG" else -1
    entry = record["entry_fill"]
    risk = abs(entry - record["stop"])
    if risk <= 0 or entry <= 0:
        raise ValueError("invalid_trade_record")
    reference_entry = record["reference_open"]
    reference_exit = record["exit_fill"] / (1 - side * slippage_per_side)
    raw_r = side * (reference_exit - reference_entry) / risk
    gross_r = side * (record["exit_fill"] - entry) / risk
    slippage_r = raw_r - gross_r
    reconstructed = gross_r - record["fee_r"] - record["funding_r"]
    if abs(reconstructed - record["net_r"]) > 1e-6:
        raise ValueError("inconsistent_trade_decomposition")
    return {**record, "raw_r": raw_r, "gross_r": gross_r, "slippage_r": slippage_r,
            "stop_width_fraction": risk / entry,
            "round_trip_cost_r": slippage_r + record["fee_r"]}


def _stats(values):
    if not values:
        return {"n": 0, "mean": None, "stderr": None}
    sd = pstdev(values) if len(values) > 1 else 0.0
    return {"n": len(values), "mean": mean(values), "stderr": sd / sqrt(len(values))}


def _bucket(width):
    for edge in STOP_WIDTH_BUCKETS:
        if width < edge:
            return f"<{edge:.2%}"
    return f">={STOP_WIDTH_BUCKETS[-1]:.2%}"


def summarize(rows):
    def block(subset):
        widths = sorted(r["stop_width_fraction"] for r in subset)
        exits = {}
        for r in subset:
            exits[r["exit_reason"]] = exits.get(r["exit_reason"], 0) + 1
        return {
            "trades": len(subset),
            "raw_r": _stats([r["raw_r"] for r in subset]),
            "slippage_r": _stats([r["slippage_r"] for r in subset]),
            "fee_r": _stats([r["fee_r"] for r in subset]),
            "funding_r": _stats([r["funding_r"] for r in subset]),
            "net_r": _stats([r["net_r"] for r in subset]),
            "median_stop_width_fraction": widths[len(widths) // 2] if widths else None,
            "exit_reasons": exits,
        }
    by_strategy = {}
    by_width = {}
    for r in rows:
        by_strategy.setdefault(r["strategy"], []).append(r)
        by_width.setdefault(_bucket(r["stop_width_fraction"]), []).append(r)
    overall = block(rows)
    raw = overall["raw_r"]
    if raw["n"] and raw["stderr"]:
        z = raw["mean"] / raw["stderr"]
        verdict = ("SIGNAL_EDGE_BEFORE_COSTS" if z > 2 else
                   "ANTI_PREDICTIVE_BEFORE_COSTS" if z < -2 else
                   "NO_DETECTABLE_EDGE_BEFORE_COSTS")
    else:
        z, verdict = None, "INSUFFICIENT_DATA"
    return {"schema": "signals.v3.cost_decomposition.1", "research_only": True,
            "out_of_sample_certified": False, "profitability_proven": False,
            "window_previously_inspected": True,
            "overall": overall, "raw_r_z": z, "diagnosis": verdict,
            "by_strategy": {k: block(v) for k, v in sorted(by_strategy.items())},
            "by_stop_width": {k: block(v) for k, v in sorted(by_width.items())}}


def main(argv=None):
    from signals_v3.pilot_replay import run
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    parser.add_argument("manifest")
    parser.add_argument("--month", required=True)
    parser.add_argument("--stride", type=int, default=12)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    records = []
    run(Path(args.directory), args.manifest, args.month, args.stride, records=records)
    rows = [decompose(r) for r in records]
    Path(args.output).write_text(json.dumps(rows) + "\n")
    print(json.dumps(summarize(rows), indent=2))


def aggregate_main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    parser.add_argument("output")
    args = parser.parse_args(argv)
    rows = []
    files = sorted(Path(args.directory).rglob("cost_rows_*.json"))
    if not files:
        raise SystemExit("FAIL_CLOSED: no monthly cost rows")
    for path in files:
        rows.extend(json.loads(path.read_text()))
    result = summarize(rows)
    result["months"] = sorted({r["month"] for r in rows})
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
