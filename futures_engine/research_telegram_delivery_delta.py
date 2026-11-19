"""Compare research Telegram delivery states against an offline baseline.

Reads SQLite and compares a local JSON baseline. Optional explicit baseline creation\nwrites a private local file (0600), never overwrites. No network or retries.
The baseline contains signal IDs and status categories, never payloads or secrets.\nNever commit or upload a real baseline.
"""
import argparse
import json
import os
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


def save_baseline(path, states):
    """Create a private, exclusive baseline file; never overwrite an existing one."""
    target = Path(path)
    if not target.parent.is_dir():
        raise FileNotFoundError("baseline_parent_missing")
    data = (json.dumps(states, sort_keys=True) + "\n").encode("utf-8")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--baseline", help="Existing private JSON baseline to compare")
    action.add_argument("--create-baseline", help="Create a new local 0600 baseline, refusing overwrite")
    args = parser.parse_args()
    current = snapshot(args.db)
    if args.baseline:
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        print(json.dumps(compare(baseline, current), sort_keys=True))
    else:
        save_baseline(args.create_baseline, current)
        print(json.dumps({"baseline_created": True, "signals": len(current),
                          "execution_authorized": False}, sort_keys=True))


if __name__ == "__main__":
    main()
