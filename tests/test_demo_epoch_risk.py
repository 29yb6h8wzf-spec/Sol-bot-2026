"""Offline Demo epoch reconciliation and preflight regression; no orders."""
import copy
import json
import os
import pytest

from demo_epoch_baseline import capture, persist_once, EpochBlocked
from demo_epoch_risk import reconcile
from demo_risk_adapter import preflight_with_epoch
from test_demo_epoch_baseline import sample, NOW


def prepared():
    old = sample()
    epoch = capture(*old, now=NOW)
    sol, xrp, provenance, _, risk = copy.deepcopy(old)
    sol["observed_at"] = xrp["observed_at"] = NOW + 2
    provenance["observed_at"] = NOW + 2
    risk["observed_at"] = NOW + 2
    risk["monitoring_gap_unresolved"] = False
    risk["prior_day_exposure_unresolved"] = False
    risk["worst_observed_drawdown_usdt"] = "0.01762774"
    risk["account_wide_unrealized_usdt"] = "0"
    provenance["day_start_utc_ms"] = epoch["day_start_utc_ms"]
    return epoch, sol, xrp, provenance, risk


def test_clean_epoch_can_be_reconciled_without_reclassifying_legacy():
    epoch, sol, xrp, provenance, risk = prepared()
    status = reconcile(epoch, sol, xrp, provenance, risk, now=NOW + 3)
    assert status["status"] == "EPOCH_RISK_RECONCILED"
    assert status["historical_unattributed_fills_archived"] == 4
    assert status["post_epoch_unattributed_fills"] == 0
    assert status["execution_authorized"] is False
    assert status["risk_preflight_eligible"] is True


def test_post_epoch_verified_fill_and_income_match():
    epoch, sol, xrp, provenance, risk = prepared()
    provenance["orders"].append({
        "order_fingerprint": "new-verified", "fill_count": 1,
        "classification": "VERIFIED_SIGNALPILOT",
        "ownership_proven": True, "symbol": "SOL/USDT:USDT"})
    provenance["total_fills"] = 5
    provenance["verified_signalpilot_fills"] = 1
    provenance["verified_realized_pnl_usdt"] = "0.20"
    provenance["verified_commissions_usdt"] = "0.02"
    provenance["registry_present"] = True
    for snap in (sol, xrp):
        snap["wallet_usdt"] = "4500.18"
        snap["available_usdt"] = "4500.18"
        snap["realized_pnl_today_usdt"] = "0.16237226"
    risk["account_wide_net_usdt"] = "0.16237226"
    risk["account_wide_realized_net_usdt"] = "0.16237226"
    status = reconcile(epoch, sol, xrp, provenance, risk, now=NOW + 3)
    assert status["post_epoch_verified_fills"] == 1


@pytest.mark.parametrize("change", [
    "new_unknown", "history_modified", "wallet_transfer",
    "income_mismatch", "daily_kill", "open_order", "stale",
    "unregistered_new_fill", "missing_legacy_order", "utc_rollover",
])
def test_fail_closed_on_unreconciled_activity(change):
    epoch, sol, xrp, provenance, risk = prepared()
    now = NOW + 3
    if change == "new_unknown":
        provenance["unattributed_fills"] = 5
        provenance["total_fills"] = 5
    elif change == "history_modified":
        provenance["orders"][0]["order_fingerprint"] = "tampered"
    elif change == "wallet_transfer":
        sol["wallet_usdt"] = xrp["wallet_usdt"] = "4501"
    elif change == "income_mismatch":
        sol["realized_pnl_today_usdt"] = xrp["realized_pnl_today_usdt"] = "0.20"
    elif change == "daily_kill":
        risk["reason"] = "DAILY_LOSS_KILL_SWITCH"
    elif change == "open_order":
        sol["orders_count"] = 1
    elif change == "stale":
        provenance["observed_at"] = NOW - 200
    elif change == "unregistered_new_fill":
        provenance["total_fills"] = 5
        provenance["verified_signalpilot_fills"] = 1
        provenance["orders"].append({
            "order_fingerprint": "unknown-new", "fill_count": 1,
            "classification": "UNREGISTERED_SPDEMO_TAG",
            "ownership_proven": False})
    elif change == "missing_legacy_order":
        provenance["orders"].pop()
    elif change == "utc_rollover":
        now = NOW + 86400
    with pytest.raises(EpochBlocked):
        reconcile(epoch, sol, xrp, provenance, risk, now=now)


def test_epoch_preflight_uses_existing_portfolio_risk(tmp_path, monkeypatch):
    epoch, sol, xrp, provenance, risk = prepared()
    status = reconcile(epoch, sol, xrp, provenance, risk, now=NOW + 3)
    baseline = tmp_path / "baseline.json"
    status_path = tmp_path / "status.json"
    persist_once(baseline, epoch)
    status_path.write_text(json.dumps(status))
    status_path.chmod(0o600)
    original_lstat = os.stat_result
    # Unit-test ownership independently of actual CI user identity.
    from pathlib import Path
    real_lstat = Path.lstat
    def test_lstat(self):
        result = real_lstat(self)
        return os.stat_result((result.st_mode, result.st_ino, result.st_dev,
            result.st_nlink, 0, result.st_gid, result.st_size, result.st_atime,
            result.st_mtime, result.st_ctime))
    monkeypatch.setattr(Path, "lstat", test_lstat)
    intent = {"symbol": "SOL/USDT:USDT", "side": "long",
              "source": "verified_85_score_engine", "score": 90,
              "entry": "100", "stop": "99", "target": "102",
              "quantity": "0.1"}
    ok, reason = preflight_with_epoch(intent, baseline_path=baseline,
                                      status_path=status_path, now=NOW + 3)
    assert ok is True, reason
    intent["quantity"] = "0.2"
    ok, reason = preflight_with_epoch(intent, baseline_path=baseline,
                                      status_path=status_path, now=NOW + 3)
    assert (ok, reason) == (False, "epoch_margin_allocation_exceeded")


def test_epoch_status_not_order_authorization():
    status = reconcile(*prepared(), now=NOW + 3)
    assert status["orders_sent"] is False
    assert status["execution_authorized"] is False
