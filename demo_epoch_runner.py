"""Supervised Demo epoch capture / reconciliation. No order writes, no deployment.

Reads authenticated Binance Demo via an exact-host GET-only transport guard.
Writes only to an explicitly provided isolated audit path, never /opt/signalpilot.
"""
import argparse
import json
import os
import tempfile
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


def run(mode, path, *, status_path=None):
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
