"""Read-only reconciliation of research Telegram delivery receipts.

No network, credentials, resend, execution or database mutations.
"""
import argparse
import json
import sqlite3
from pathlib import Path


def audit(db_path):
    path = Path(db_path).resolve(strict=True)
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT o.signal_id, d.status, "
            "CASE WHEN EXISTS (SELECT 1 FROM sandbox_publish_log p "
            "WHERE p.signal_id=o.signal_id) THEN 1 ELSE 0 END "
            "FROM research_outbox o "
            "LEFT JOIN binance_telegram_delivery d ON d.signal_id=o.signal_id"
        ).fetchall()
        counts = {"delivered_recorded": 0, "unconfirmed": 0,
                  "missing_delivery_receipt": 0, "other_status": 0,
                  "sandbox_publish_logged": 0}
        for _sid, status, published in rows:
            if status == "DELIVERED_OWNER_ONLY":
                counts["delivered_recorded"] += 1
            elif status == "UNCONFIRMED":
                counts["unconfirmed"] += 1
            elif status is None:
                counts["missing_delivery_receipt"] += 1
            else:
                counts["other_status"] += 1
            counts["sandbox_publish_logged"] += int(bool(published))
        return {"total_outbox": len(rows), "counts": counts,
                "delivery_confirmed_by_telegram": False,
                "execution_authorized": False}
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.db), sort_keys=True))


if __name__ == "__main__":
    main()
