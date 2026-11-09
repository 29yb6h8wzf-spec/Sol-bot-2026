"""Demo-only reconciliation epoch: preserve legacy fills, start a clean audit boundary.

This is an audit and risk-readiness component, NOT a trading authorization.
The pre-epoch unknown fills remain permanently recorded as UNKNOWN_EXTERNAL.
The only acceptable starting point is a fresh, authenticated, account-wide
flat Demo snapshot. No API mutations, no orders, no production deployment.
"""
import hashlib
import json
import os
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

CAPITAL = Decimal("150")
DAILY_CAP = Decimal("7.50")
SNAPSHOT_AGE = 10
AUDIT_AGE = 90


class EpochBlocked(ValueError):
    pass


def amount(raw):
    if isinstance(raw, bool):
        raise EpochBlocked("invalid_amount")
    try:
        x = Decimal(str(raw))
    except (TypeError, ValueError, InvalidOperation):
        raise EpochBlocked("invalid_amount") from None
    if not x.is_finite():
        raise EpochBlocked("nonfinite_amount")
    return x


def _fresh(doc, now, max_age):
    if not isinstance(doc, dict) or type(doc.get("observed_at")) is not int:
        raise EpochBlocked("missing_observation")
    if not 0 <= now - doc["observed_at"] <= max_age:
        raise EpochBlocked("stale_observation")


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash(obj):
    return hashlib.sha256(_canonical(obj).encode("utf-8")).hexdigest()


def capture(sol, xrp, provenance, reconciliation, risk, *, now=None):
    """Capture evidence, not approval, at a verified flat account boundary."""
    now = int(time.time()) if now is None else int(now)
    for snap in (sol, xrp):
        _fresh(snap, now, SNAPSHOT_AGE)
        if snap.get("endpoint") != "https://demo-fapi.binance.com":
            raise EpochBlocked("not_demo")
        if snap.get("authenticated") is not True or snap.get("one_way") is not True:
            raise EpochBlocked("account_not_authenticated_one_way")
        if any(snap.get(k) != 0 for k in
               ("positions_count", "orders_count", "algo_orders_count")):
            raise EpochBlocked("account_not_flat")
        if snap.get("margin_type") != "isolated" or snap.get("leverage") != 2:
            raise EpochBlocked("configuration_not_2x_isolated")
        if amount(snap.get("wallet_usdt")) <= 0 or amount(snap.get("available_usdt")) <= 0:
            raise EpochBlocked("invalid_balance")
    for key in ("wallet_usdt", "available_usdt", "realized_pnl_today_usdt"):
        if amount(sol[key]) != amount(xrp[key]):
            raise EpochBlocked("inconsistent_account_snapshots")
    if abs(sol["observed_at"] - xrp["observed_at"]) > 5:
        raise EpochBlocked("non_atomic_account_observation")
    for doc in (provenance, reconciliation, risk):
        _fresh(doc, now, AUDIT_AGE)
        if doc.get("execution_authorized") is not False:
            raise EpochBlocked("unexpected_execution_authorization")
    if (provenance.get("source") != "binance_demo_order_provenance_read_only"
            or provenance.get("status") != "AUDIT_ONLY_NOT_EXECUTABLE"):
        raise EpochBlocked("untrusted_provenance")
    unknown = provenance.get("unattributed_fills")
    if type(unknown) is not int or unknown < 0:
        raise EpochBlocked("invalid_legacy_fill_count")
    if (provenance.get("total_fills") !=
            unknown + provenance.get("verified_signalpilot_fills", -1)):
        raise EpochBlocked("legacy_fill_accounting_mismatch")
    if (reconciliation.get("source") != "signalpilot_demo_reconciliation_guard_read_only"
            or reconciliation.get("status") != "BLOCKED_UNRECONCILED"
            or reconciliation.get("unattributed_fills_today") != unknown
            or reconciliation.get("prior_day_exposure_unresolved") is not False
            or reconciliation.get("monitoring_gap_unresolved") is not False
            or reconciliation.get("open_exposure_now") is not False):
        raise EpochBlocked("reconciliation_not_safe_for_new_epoch")
    if (risk.get("status") != "BLOCKED"
            or risk.get("allocation_ledger_reconciled") is not False):
        raise EpochBlocked("risk_monitor_not_fail_closed")
    if risk.get("reason") == "DAILY_LOSS_KILL_SWITCH":
        raise EpochBlocked("daily_kill_switch_latched")
    day_pnl = amount(sol["realized_pnl_today_usdt"])
    if day_pnl <= -DAILY_CAP:
        raise EpochBlocked("daily_loss_exhausted")
    if amount(risk.get("account_wide_net_usdt")) <= -DAILY_CAP:
        raise EpochBlocked("account_wide_daily_loss_exhausted")
    # Do not reset the UTC daily loss counter; preserve full-day PnL.
    if day_pnl != amount(risk.get("account_wide_realized_net_usdt")):
        raise EpochBlocked("income_monitor_disagrees")
    historical = {
        "classification": "UNATTRIBUTED_PRE_EPOCH_NOT_SIGNALPILOT",
        "fill_count": unknown,
        "order_classifications": provenance.get("order_classifications"),
        "unattributed_history_unresolved": reconciliation.get("unattributed_history_unresolved"),
        "legacy_income_gap_usdt": reconciliation.get("account_realized_gap_usdt"),
        "legacy_commission_gap_usdt": reconciliation.get("account_commission_gap_usdt"),
        "legacy_funding_unattributed_usdt": reconciliation.get("account_funding_unattributed_usdt"),
    }
    if not isinstance(historical["order_classifications"], dict):
        raise EpochBlocked("legacy_classifications_missing")
    epoch = {
        "schema_version": 1,
        "source": "signalpilot_demo_new_epoch_baseline",
        "endpoint": "https://demo-fapi.binance.com",
        "epoch_started_at": now,
        "day_start_utc_ms": reconciliation.get("day_start_utc_ms"),
        "wallet_usdt": str(amount(sol["wallet_usdt"])),
        "available_usdt": str(amount(sol["available_usdt"])),
        "account_day_pnl_at_start_usdt": str(day_pnl),
        "effective_capital_usdt": str(min(amount(sol["wallet_usdt"]), CAPITAL)),
        "daily_loss_cap_usdt": str(DAILY_CAP),
        "legacy_audit": historical,
        "account_flat_at_baseline": True,
        "mode": "DEMO_ONLY",
        "status": "BASELINE_CAPTURED_REQUIRES_CONTINUOUS_RECONCILIATION",
        "allocation_ledger_reconciled": False,
        "execution_authorized": False,
        "orders_sent": False,
    }
    epoch["evidence_sha256"] = _hash({
        "sol": sol, "xrp": xrp, "provenance": provenance,
        "reconciliation": reconciliation, "risk": risk,
    })
    epoch["baseline_sha256"] = _hash(epoch)
    return epoch


def persist_once(path, epoch):
    """Write-once 0600 baseline. Never overwrite an existing audit boundary."""
    if not isinstance(epoch, dict) or epoch.get("source") != "signalpilot_demo_new_epoch_baseline":
        raise EpochBlocked("invalid_baseline")
    path = Path(path)
    if not path.parent.is_dir() or path.is_symlink():
        raise EpochBlocked("invalid_baseline_path")
    data = (_canonical(epoch) + "\n").encode("utf-8")
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    return path


def inspect(epoch):
    """Validate saved baseline integrity; NEVER infer trading approval from it."""
    if not isinstance(epoch, dict):
        raise EpochBlocked("invalid_baseline")
    expected = epoch.get("baseline_sha256")
    payload = {k: v for k, v in epoch.items() if k != "baseline_sha256"}
    if not isinstance(expected, str) or expected != _hash(payload):
        raise EpochBlocked("baseline_integrity_mismatch")
    if (epoch.get("source") != "signalpilot_demo_new_epoch_baseline"
            or epoch.get("mode") != "DEMO_ONLY"
            or epoch.get("execution_authorized") is not False
            or epoch.get("status") != "BASELINE_CAPTURED_REQUIRES_CONTINUOUS_RECONCILIATION"):
        raise EpochBlocked("untrusted_baseline")
    return {"baseline_integrity": "VERIFIED", "legacy_fill_count":
            epoch["legacy_audit"]["fill_count"], "execution_authorized": False}
