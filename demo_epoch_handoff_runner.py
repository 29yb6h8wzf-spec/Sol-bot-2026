"""One-shot, GET-only bridge from real SignalPilot inbox to Demo epoch gate.

Never synthesizes signals, reserves an order, or calls Binance order endpoints.
Only fresh, independently recalculated candidates can become handoff-ready.
"""
import argparse
import json
import sqlite3
import time
from pathlib import Path
from demo_epoch_handoff import prepare, epoch_paths
from demo_epoch_runner import run as refresh_epoch
from demo_account_snapshot import demo_client_from_aws
from demo_execution_gate import DemoGateBlocked


def fresh_inbox(path, *, now=None):
    now = int(time.time()) if now is None else int(now)
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5) as db:
        rows = db.execute(
            "SELECT payload FROM signals ORDER BY received_at DESC LIMIT 100"
        ).fetchall()
    fresh = []
    for (raw,) in rows:
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        stamp = payload.get("timestamp")
        if type(stamp) is int and 0 <= now - stamp <= 120:
            fresh.append(payload)
    return fresh


def observe_once(inbox_path, *, baseline_path=None, status_path=None,
                 now=None, exchange_factory=demo_client_from_aws,
                 refresh=refresh_epoch, prepare_handoff=prepare):
    now = int(time.time()) if now is None else int(now)
    defaults = epoch_paths(now)
    baseline_path = defaults[0] if baseline_path is None else baseline_path
    status_path = defaults[1] if status_path is None else status_path
    signals = fresh_inbox(inbox_path, now=now)
    if not signals:
        return {"mode": "DEMO_ONLY", "status": "NO_FRESH_VERIFIED_SIGNAL",
                "fresh_inbox_candidates": 0, "ready": 0,
                "orders_sent": False, "execution_authorized": False}
    # Risk is recalculated from actual authenticated Binance Demo GET endpoints.
    result = refresh("reconcile", baseline_path, status_path=status_path)
    if result.get("status") != "EPOCH_RISK_RECONCILED":
        raise DemoGateBlocked("epoch_reconciliation_not_ready")
    exchange = exchange_factory()
    ready = []
    blocked = {}
    try:
        for payload in signals:
            try:
                handoff = prepare_handoff(
                    payload, exchange, baseline_path=baseline_path,
                    status_path=status_path, now=now)
                ready.append({"signal_id": handoff["intent"]["signal_id"],
                              "symbol": handoff["intent"]["symbol"],
                              "event_key": handoff["intent"]["event_key"]})
            except Exception as exc:
                reason = str(exc) if isinstance(exc, (DemoGateBlocked, ValueError)) else type(exc).__name__
                blocked[reason] = blocked.get(reason, 0) + 1
    finally:
        if hasattr(exchange, "close"):
            exchange.close()
    return {"mode": "DEMO_ONLY", "status": "HANDOFF_READY_NOT_SUBMITTED" if ready
            else "NO_ELIGIBLE_VERIFIED_SIGNAL",
            "fresh_inbox_candidates": len(signals), "ready": len(ready),
            "blocked_reasons": blocked, "orders_sent": False,
            "execution_authorized": False}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inbox", default="/opt/signalpilot/signal-inbox.sqlite3")
    p.add_argument("--baseline", default=None)
    p.add_argument("--status", default=None)
    args = p.parse_args()
    print(json.dumps(observe_once(args.inbox, baseline_path=args.baseline,
                                  status_path=args.status), sort_keys=True))


if __name__ == "__main__":
    main()
