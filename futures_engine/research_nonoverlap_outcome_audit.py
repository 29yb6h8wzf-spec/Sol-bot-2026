"""Descriptive, research-only non-overlapping outcome audit.

Selection is chronological per symbol and based on next-open availability;
never select events using their future return. Historical holdout is NOT locked OOS.
"""
import argparse
import json
from pathlib import Path


def _stats(events):
    return {"count": len(events),
            "wins": sum(e["net_pct"] > 0 for e in events),
            "losses": sum(e["net_pct"] < 0 for e in events),
            "mean_net_pct": round(sum(e["net_pct"] for e in events) / len(events), 6) if events else None,
            "sum_net_pct_uncompounded": round(sum(e["net_pct"] for e in events), 6)}


def audit(report):
    if report.get("research_only") is not True or report.get("execution_authorized") is not False:
        raise ValueError("research_gate")
    events = report.get("events")
    if not isinstance(events, list):
        raise ValueError("invalid_events")
    ordered = sorted(events, key=lambda e: (e["entry_open_ms"], e["symbol"],
                                             e["strategy"], e["direction"]))
    accepted = []
    last_exit_by_symbol = {}
    for e in ordered:
        symbol, entry, exit_time = e["symbol"], e["entry_open_ms"], e["exit_open_ms"]
        if entry > exit_time or entry < 0:
            raise ValueError("invalid_event_times")
        if entry <= last_exit_by_symbol.get(symbol, -1):
            continue
        accepted.append(e)
        last_exit_by_symbol[symbol] = exit_time
    by_symbol = {symbol: _stats([e for e in accepted if e["symbol"] == symbol])
                 for symbol in sorted({e["symbol"] for e in ordered})}
    by_strategy = {strategy: _stats([e for e in accepted if e["strategy"] == strategy])
                   for strategy in sorted({e["strategy"] for e in ordered})}
    # Descriptive chronological 70/30 split; not a prospective or sealed OOS test.
    cutoff_index = int(len(accepted) * 0.7)
    return {"research_only": True, "execution_authorized": False,
            "warning": "Historical exploratory analysis; NOT sealed out-of-sample validation",
            "policy": "one concurrent hypothetical position per symbol; earliest next-open first",
            "all_candidate_events": _stats(ordered),
            "nonoverlap": _stats(accepted),
            "overlaps_skipped": len(ordered) - len(accepted),
            "by_symbol": by_symbol, "by_strategy": by_strategy,
            "chronological_descriptive": {"first_70pct": _stats(accepted[:cutoff_index]),
                                          "last_30pct": _stats(accepted[cutoff_index:])},
            "accepted_events": accepted}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    with Path(args.input).open(encoding="utf-8") as f:
        result = audit(json.load(f))
    with Path(args.output).open("x", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")
    print(json.dumps({k: result[k] for k in
                      ("nonoverlap", "overlaps_skipped", "by_symbol", "by_strategy",
                       "chronological_descriptive")}, sort_keys=True))


if __name__ == "__main__":
    main()
