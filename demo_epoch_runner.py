"""Supervised Demo epoch capture / reconciliation. No order writes, no deployment.

Reads authenticated Binance Demo via an exact-host GET-only transport guard.
Writes only to an explicitly provided isolated audit path, never /opt/signalpilot.
"""
import argparse
import json
import os
import tempfile
from pathlib import Path

from demo_account_snapshot import demo_client_from_aws, read_snapshots
from demo_epoch_baseline import capture, inspect, persist_once, EpochBlocked
from demo_epoch_risk import reconcile
from demo_provenance_observer import inspect as inspect_provenance
from demo_virtual_allocation import trusted_json
from demo_risk_monitor import assess as assess_account_risk
import time


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


def save_risk_status(path, status):
    path = isolated_path(path)
    fd, temp = tempfile.mkstemp(prefix=".demo-epoch-risk-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(status, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def fresh_risk_from_authenticated_snapshot(snap, provenance):
    """Re-evaluate existing latched monitor risk without writing production."""
    now = int(time.time())
    root = Path("/opt/signalpilot")
    prior = trusted_json(root, "demo-risk-monitor-state.json")
    reconciliation = trusted_json(root, "demo-reconciliation-status.json")
    stamp = reconciliation.get("observed_at")
    if type(stamp) is not int or not 0 <= now - stamp <= 900:
        raise EpochBlocked("reconciliation_monitoring_gap")
    if (reconciliation.get("monitoring_gap_unresolved") is not False
            or reconciliation.get("prior_day_exposure_unresolved") is not False):
        raise EpochBlocked("unresolved_monitoring_or_prior_day_exposure")
    common = {"observed_at": snap["observed_at"], "orders_sent": False}
    pnl = {**common, "source": "binance_demo_account_wide_income_read_only",
           "day_start_utc_ms": (now // 86400) * 86400000,
           "net_income_usdt": snap["realized_pnl_today_usdt"]}
    exposure = {**common, "source": "binance_demo_account_wide_unrealized_read_only",
                "unrealized_pnl_usdt": "0", "open_position_count": snap["positions_count"],
                "exposed_symbols": [], "allocation_ledger_reconciled": False}
    account = {**common, "source": "binance_demo_observation_only",
               "exposed_symbols": [], "open_orders": {"ALL": snap["orders_count"]},
               "open_algo_orders": {"ALL": snap["algo_orders_count"]}}
    risk, _ = assess_account_risk(pnl, exposure, account, prior, now=now)
    if provenance.get("unattributed_fills", 0) and risk["reason"] != "DAILY_LOSS_KILL_SWITCH":
        risk["reason"] = "UNATTRIBUTED_DEMO_FILLS"
    risk["observed_at"] = now
    risk["monitoring_gap_unresolved"] = False
    risk["prior_day_exposure_unresolved"] = False
    return risk


def run(mode, path, *, status_path=None):
    path = isolated_path(path)
    exchange = demo_client_from_aws()
    try:
        provenance = inspect_provenance(exchange)
        snapshots = read_snapshots(exchange)
        sol, xrp = snapshots["SOLUSDT"], snapshots["XRPUSDT"]
        risk = fresh_risk_from_authenticated_snapshot(sol, provenance)
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
            if status_path is not None:
                if isolated_path(status_path) == path:
                    raise EpochBlocked("status_must_not_overwrite_baseline")
                save_risk_status(status_path, status)
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
    parser.add_argument("--status", default=None)
    args = parser.parse_args()
    result = run(args.mode, args.baseline, status_path=args.status)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
