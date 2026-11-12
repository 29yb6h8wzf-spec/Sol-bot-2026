"""Read-only, complete current priced-universe liquidity capture.

Fail closed: partial or stale observations never qualify as a complete universe.
Current snapshots cannot establish historical point-in-time eligibility.
"""
import json
import time
from pathlib import Path

from signals_v3.collect_current_liquidity import public_json, snapshot_symbol
from signals_v3.discover_current_price_candidates import discover_current_price_candidates


def capture_full_current_universe(fetch=public_json, clock_ms=None):
    if clock_ms is None:
        clock_ms = lambda: int(time.time() * 1000)
    started = clock_ms()
    cache = {}
    def shared_fetch(path, params=None):
        if path == "/fapi/v1/exchangeInfo" and params is None:
            if path not in cache:
                cache[path] = fetch(path)
            return cache[path]
        return fetch(path, params) if params is not None else fetch(path)
    symbols = discover_current_price_candidates(shared_fetch)
    if not symbols:
        raise ValueError("no_price_eligible_markets")
    snapshots = []
    previous_observed_at_ms = started
    for symbol in symbols:
        snapshot = snapshot_symbol(symbol, fetch=shared_fetch, clock_ms=clock_ms)
        if snapshot["symbol"] != symbol or snapshot["observed_at_ms"] < started:
            raise ValueError("invalid_market_snapshot")
        observed = snapshot["observed_at_ms"]
        if type(observed) is not int or observed < previous_observed_at_ms:
            raise ValueError("non_monotonic_market_snapshot")
        previous_observed_at_ms = observed
        snapshots.append(snapshot)
    finished = clock_ms()
    if finished < previous_observed_at_ms:
        raise ValueError("snapshot_timestamp_after_capture")
    if finished < started or finished - started > 300_000:
        raise ValueError("complete_capture_too_slow")
    if len(snapshots) != len(symbols) or len({x["symbol"] for x in snapshots}) != len(symbols):
        raise ValueError("incomplete_market_capture")
    return {
        "schema": "signals.v3.current_universe_capture.1",
        "current_only": True,
        "historical_universe_verified": False,
        "complete_market_capture": True,
        "started_at_ms": started,
        "finished_at_ms": finished,
        "candidate_count": len(symbols),
        "captured_count": len(snapshots),
        "snapshots": snapshots,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    args = parser.parse_args()
    report = capture_full_current_universe()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"candidate_count": report["candidate_count"],
                      "captured_count": report["captured_count"],
                      "complete_market_capture": True,
                      "current_only": True}))


if __name__ == "__main__":
    main()
