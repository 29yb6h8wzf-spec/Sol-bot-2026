"""Compare research Telegram delivery states against an offline baseline.

Reads SQLite and a local JSON baseline only. No network, writes or retries.
The baseline contains signal IDs and status categories, never payloads or secrets.
"""
import argparse
import json
import sqlite3
from pathlib import Path

CATEGORIES = ("delivered_recorded", "unconfirmed", "missing_delivery_receipt", "other_status")


def snapshot(db_path):
    path = Path(db_path).resolve(strict=True)
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as conn:
        rows = conn.execute(
            "SELECT o.signal_id, d.status FROM research_outbox o "
            "LEFT JOIN binance_telegram_delivery d ON d.signal_id=o.signal_id"
        ).fetchall()
    states = {}
    for sid, status in rows:
        if status == "DELIVERED_OWNER_ONLY":
            category = "delivered_recorded"
        elif status == "UNCONFIRMED":
            category = "unconfirmed"
        elif status is None:
            category = "missing_delivery_receipt"
        else:
            category = "other_status"
        states[sid] = category
    return states


def compare(baseline, current):
    if not isinstance(baseline, dict) or not isinstance(current, dict):
        raise ValueError("invalid_snapshot")
    if any(not isinstance(k, str) or v not in CATEGORIES for k, v in list(baseline.items()) + list(current.items())):
        raise ValueError("invalid_snapshot_category")
    old = set(baseline)
    new = set(current)
    changed = {sid for sid in old & new if baseline[sid] != current[sid]}
    unresolved = set(CATEGORIES) - {"delivered_recorded"}
    return {
        "baseline_total": len(old),
        "current_total": len(new),
        "new_signals": len(new - old),
        "new_unresolved": sum(current[sid] in unresolved for sid in new - old),
        "resolved_existing": sum(baseline[sid] in unresolved and current[sid] == "delivered_recorded" for sid in changed),
        "existing_became_unresolved": sum(baseline[sid] == "delivered_recorded" and current[sid] in unresolved for sid in changed),
        "other_existing_status_changes": sum(not (
            (baseline[sid] in unresolved and current[sid] == "delivered_recorded") or
            (baseline[sid] == "delivered_recorded" and current[sid] in unresolved)
        ) for sid in changed),
        "missing_from_current": len(old - new),
        "execution_authorized": False,
        "delivery_confirmed_by_telegram": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--baseline", help="Existing JSON baseline with signal IDs and categories")
    args = parser.parse_args()
    current = snapshot(args.db)
    if args.baseline:
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        print(json.dumps(compare(baseline, current), sort_keys=True))
    else:
        # Output may contain signal IDs. Keep locally; never upload as CI artifact.
        print(json.dumps(current, sort_keys=True))


if __name__ == "__main__":
    main()
