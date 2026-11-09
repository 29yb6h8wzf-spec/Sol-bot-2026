"""Supervised Demo epoch capture / reconciliation. No order writes, no deployment.

Reads authenticated Binance Demo via an exact-host GET-only transport guard.
Writes only to an explicitly provided isolated audit path, never /opt/signalpilot.
"""
import argparse
import json
import os
from pathlib import Path

from demo_account_snapshot import demo_client_from_aws, read_snapshot
from demo_epoch_baseline import capture, inspect, persist_once, EpochBlocked
from demo_epoch_risk import reconcile
from demo_provenance_observer import inspect as inspect_provenance
from demo_virtual_allocation import trusted_json


def isolated_path(raw):
    path = Path(raw).resolve(strict=False)
    root = Path("/opt/signalpilot-audit-worktree").resolve(strict=False)
    if root not in path.parents or path == root:
        raise EpochBlocked("output_must_be_isolated_audit_worktree")
    if not path.parent.is_dir() or path.is_symlink():
        raise EpochBlocked("invalid_audit_path")
    return path


def trusted_baseline(path):
    path = isolated_path(path)
    st = path.lstat()
    if not path.is_file() or path.is_symlink() or st.st_uid != 0 or st.st_mode & 0o077:
        raise EpochBlocked("baseline_file_untrusted")
    epoch = json.loads(path.read_text(encoding="utf-8"))
    inspect(epoch)
    return epoch


def run(mode, path):
    path = isolated_path(path)
    exchange = demo_client_from_aws()
    try:
        sol = read_snapshot(exchange, "SOLUSDT")
        xrp = read_snapshot(exchange, "XRPUSDT")
        provenance = inspect_provenance(exchange)
        risk = trusted_json(Path("/opt/signalpilot"), "demo-risk-monitor-status.json")
        if mode == "capture":
            reconciliation = trusted_json(
                Path("/opt/signalpilot"), "demo-reconciliation-status.json")
            epoch = capture(sol, xrp, provenance, reconciliation, risk)
            persist_once(path, epoch)
            return {"mode": "DEMO_ONLY", "status": epoch["status"],
                    "legacy_fills_archived": epoch["legacy_audit"]["fill_count"],
                    "baseline_sha256": epoch["baseline_sha256"],
                    "orders_sent": False}
        if mode == "reconcile":
            epoch = trusted_baseline(path)
            status = reconcile(epoch, sol, xrp, provenance, risk)
            return {"mode": "DEMO_ONLY", "status": status["status"],
                    "post_epoch_unattributed_fills": status["post_epoch_unattributed_fills"],
                    "risk_preflight_eligible": status["risk_preflight_eligible"],
                    "execution_authorized": False, "orders_sent": False}
        raise EpochBlocked("invalid_mode")
    finally:
        if hasattr(exchange, "close"):
            exchange.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("capture", "reconcile"))
    parser.add_argument("--baseline", required=True)
    args = parser.parse_args()
    result = run(args.mode, args.baseline)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
