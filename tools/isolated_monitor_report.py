"""Read-only summary of SignalPilot isolated monitor JSONL; never places orders.

Usage: python -m tools.isolated_monitor_report /path/to/isolated-monitor.jsonl
Outputs aggregate evidence, not secrets, payloads, or account credentials.
"""
import argparse
import collections
import json
from pathlib import Path


def summarize(lines):
    events = collections.Counter()
    symbols = collections.Counter()
    blocked = collections.Counter()
    failed_conditions = collections.Counter()
    candidates = []
    timestamps = []
    malformed = 0
    scan_qualified = 0
    telegram_sent = 0
    orders_sent = 0
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            if not isinstance(item, dict) or not isinstance(item.get("event"), str):
                raise ValueError("invalid event")
        except (ValueError, TypeError):
            malformed += 1
            continue
        kind = item["event"]
        events[kind] += 1
        if type(item.get("at")) is int:
            timestamps.append(item["at"])
        if kind == "scan":
            symbols[str(item.get("symbol", "unknown"))] += 1
            if type(item.get("qualified")) is int:
                scan_qualified += item["qualified"]
        if kind == "candidate":
            score = item.get("score")
            eligible = type(score) is int and score >= 85
            candidates.append({"eligible": eligible, "blocked": item.get("blocked") is True})
            if item.get("blocked") is True:
                blocked[str(item.get("block_condition") or "unspecified")] += 1
        if kind == "condition" and item.get("passed") is False:
            failed_conditions[str(item.get("strategy", "?")) + ":" + str(item.get("name", "?"))] += 1
        if item.get("telegram_sent") is True:
            telegram_sent += 1
        elif type(item.get("telegram_sent")) is int:
            telegram_sent += item["telegram_sent"]
        if type(item.get("orders_sent")) is int:
            orders_sent += item["orders_sent"]
    return {
        "records": sum(events.values()), "malformed": malformed,
        "events": dict(sorted(events.items())),
        "scans_by_symbol": dict(sorted(symbols.items())),
        "first_at": min(timestamps) if timestamps else None,
        "last_at": max(timestamps) if timestamps else None,
        "candidate_count": len(candidates),
        "candidate_at_least_85": sum(x["eligible"] for x in candidates),
        "eligible_candidates_blocked": sum(x["eligible"] and x["blocked"] for x in candidates),
        "blocked_by_reason": dict(sorted(blocked.items())),
        "failed_conditions": dict(sorted(failed_conditions.items())),
        "scan_qualified_count": scan_qualified,
        "telegram_sent_events": telegram_sent,
        "orders_sent_count": orders_sent,
        "e2e_verified": False,
        "note": "Counts are monitor observations, not proof of Telegram delivery, demo fills, or production execution.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl", type=Path)
    args = parser.parse_args()
    with args.jsonl.open(encoding="utf-8") as handle:
        print(json.dumps(summarize(handle), sort_keys=True, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
