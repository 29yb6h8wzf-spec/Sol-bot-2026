"""New-epoch Binance Demo risk reconciliation, never an order executor.

Legacy unknown orders remain in the immutable baseline. New activity must
be independently attributed to a trusted SignalPilot order registry and the
full account income delta must match the attributable PnL and fees exactly.
No live Binance endpoint, no order creation, no service deployment.
"""
import time
from decimal import Decimal
from demo_epoch_baseline import (
    EpochBlocked, amount, inspect, _fresh, SNAPSHOT_AGE, AUDIT_AGE, DAILY_CAP,
)

ALLOWED_LEGACY_REASON = frozenset({
    "UNATTRIBUTED_DEMO_FILLS", "UNATTRIBUTED_HISTORICAL_FILLS",
    "ALLOCATION_LEDGER_NOT_RECONCILED",
})


def reconcile(epoch, sol, xrp, provenance, risk, *, now=None):
    now = int(time.time()) if now is None else int(now)
    inspect(epoch)
    if type(epoch.get("epoch_started_at")) is not int or not 0 <= now - epoch["epoch_started_at"]:
        raise EpochBlocked("invalid_epoch_time")
    if now // 86400 != epoch["epoch_started_at"] // 86400:
        raise EpochBlocked("utc_rollover_requires_new_baseline")
    if epoch.get("day_start_utc_ms") != (now // 86400) * 86400000:
        raise EpochBlocked("epoch_day_mismatch")
    for snap in (sol, xrp):
        _fresh(snap, now, SNAPSHOT_AGE)
        if (snap.get("endpoint") != "https://demo-fapi.binance.com"
                or snap.get("authenticated") is not True
                or snap.get("one_way") is not True
                or snap.get("margin_type") != "isolated"
                or snap.get("leverage") != 2):
            raise EpochBlocked("invalid_demo_configuration")
        if any(snap.get(key) != 0 for key in
               ("positions_count", "orders_count", "algo_orders_count")):
            raise EpochBlocked("demo_not_flat")
        if snap["observed_at"] < epoch["epoch_started_at"]:
            raise EpochBlocked("snapshot_predates_epoch")
    if abs(sol["observed_at"] - xrp["observed_at"]) > 5:
        raise EpochBlocked("non_atomic_account_snapshot")
    for key in ("wallet_usdt", "available_usdt", "realized_pnl_today_usdt"):
        if amount(sol[key]) != amount(xrp[key]):
            raise EpochBlocked("inconsistent_account_snapshots")
    _fresh(provenance, now, AUDIT_AGE)
    _fresh(risk, now, AUDIT_AGE)
    if provenance["observed_at"] < epoch["epoch_started_at"]:
        raise EpochBlocked("provenance_predates_epoch")
    if (provenance.get("source") != "binance_demo_order_provenance_read_only"
            or provenance.get("status") != "AUDIT_ONLY_NOT_EXECUTABLE"
            or provenance.get("day_start_utc_ms") != epoch["day_start_utc_ms"]
            or provenance.get("execution_authorized") is not False):
        raise EpochBlocked("invalid_provenance")
    if (risk.get("status") != "BLOCKED"
            or risk.get("reason") not in ALLOWED_LEGACY_REASON
            or risk.get("allocation_ledger_reconciled") is not False
            or risk.get("execution_authorized") is not False
            or risk.get("monitoring_gap_unresolved") is not False
            or risk.get("prior_day_exposure_unresolved") is not False):
        raise EpochBlocked("monitor_not_safe")
    if amount(risk.get("worst_observed_drawdown_usdt")) >= DAILY_CAP:
        raise EpochBlocked("daily_loss_latched")
    if (amount(risk.get("account_wide_unrealized_usdt")) != 0
            or amount(risk.get("account_wide_net_usdt")) !=
            amount(sol["realized_pnl_today_usdt"])
            or amount(risk.get("account_wide_realized_net_usdt")) !=
            amount(sol["realized_pnl_today_usdt"])):
        raise EpochBlocked("risk_accounting_mismatch")
    if amount(sol["realized_pnl_today_usdt"]) <= -DAILY_CAP:
        raise EpochBlocked("daily_loss_exhausted")
    legacy = epoch["legacy_audit"]
    rows = provenance.get("orders")
    if not isinstance(rows, list):
        raise EpochBlocked("missing_order_inventory")
    index = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("order_fingerprint"), str):
            raise EpochBlocked("invalid_order_inventory")
        fingerprint = row["order_fingerprint"]
        if fingerprint in index:
            raise EpochBlocked("duplicate_order_fingerprint")
        index[fingerprint] = row
    for old in legacy["orders"]:
        current = index.get(old["order_fingerprint"])
        if current != old:
            raise EpochBlocked("historical_order_evidence_changed")
    if (provenance.get("unattributed_fills") != legacy["fill_count"]
            or type(provenance.get("total_fills")) is not int
            or provenance["total_fills"] < legacy["total_fills"]):
        raise EpochBlocked("new_unattributed_or_missing_fills")
    new_rows = [row for fingerprint, row in index.items()
                if fingerprint not in {x["order_fingerprint"] for x in legacy["orders"]}]
    if any(row.get("classification") != "VERIFIED_SIGNALPILOT"
           or row.get("ownership_proven") is not True for row in new_rows):
        raise EpochBlocked("post_epoch_order_not_owned")
    new_fills = provenance["total_fills"] - legacy["total_fills"]
    if sum(row.get("fill_count", 0) for row in new_rows) != new_fills:
        raise EpochBlocked("post_epoch_fill_count_mismatch")
    if (provenance.get("verified_signalpilot_fills") != legacy["verified_fills"] + new_fills
            or (new_fills > 0 and provenance.get("registry_present") is not True)):
        raise EpochBlocked("post_epoch_registry_missing")
    realized_delta = (amount(provenance.get("verified_realized_pnl_usdt"))
                      - amount(legacy["verified_realized_pnl_usdt"]))
    fee_delta = (amount(provenance.get("verified_commissions_usdt"))
                 - amount(legacy["verified_commissions_usdt"]))
    if fee_delta < 0:
        raise EpochBlocked("negative_post_epoch_fees")
    pnl_delta = (amount(sol["realized_pnl_today_usdt"])
                 - amount(epoch["account_day_pnl_at_start_usdt"]))
    wallet_delta = amount(sol["wallet_usdt"]) - amount(epoch["wallet_usdt"])
    if pnl_delta != realized_delta - fee_delta or wallet_delta != pnl_delta:
        raise EpochBlocked("account_wide_income_or_transfer_unattributed")
    if amount(sol["available_usdt"]) <= 0:
        raise EpochBlocked("insufficient_available_margin")
    # Risk approval for this clean epoch is not an order authorization. A
    # separate Demo-only executor must still validate fresh price/qty/SL/TP.
    return {
        "source": "signalpilot_demo_epoch_reconciler",
        "status": "APPROVED",
        "observed_at": now,
        "baseline_sha256": epoch["baseline_sha256"],
        "epoch_started_at": epoch["epoch_started_at"],
        "historical_unattributed_fills_archived": legacy["fill_count"],
        "post_epoch_verified_fills": new_fills,
        "post_epoch_unattributed_fills": 0,
        "account_day_pnl_usdt": str(amount(sol["realized_pnl_today_usdt"])),
        "account_day_loss_cap_usdt": str(DAILY_CAP),
        "capital_allocation_usdt": str(min(amount(sol["wallet_usdt"]), Decimal("150"))),
        "allocation_ledger_reconciled": True,
        "execution_authorized": True,
        "mode": "DEMO_ONLY",
        "orders_sent": False,
    }
