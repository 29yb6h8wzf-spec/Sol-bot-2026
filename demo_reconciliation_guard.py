"""Read-only, fail-closed Binance DEMO reconciliation and UTC rollover guard.

Compares account-wide income to exchange-confirmed SignalPilot fills. Records
unattributed history and prior-day exposure across UTC midnight; neither is
silently cleared by the daily API window. This does not authorize execution.
"""
import json
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from demo_account_observer import save_observation
from demo_risk_monitor import check_observation
from demo_virtual_allocation import trusted_json

ROOT = Path("/opt/signalpilot")
STATE = "demo-reconciliation-state.json"
OUTPUT = "demo-reconciliation-status.json"
MAX_GAP_SECONDS = 900


def amount(value):
    try:
        result = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        raise ValueError("invalid_reconciliation_amount") from None
    if not result.is_finite():
        raise ValueError("nonfinite_reconciliation_amount")
    return result


def utc_day(now):
    return datetime.fromtimestamp(now, timezone.utc).date().isoformat()


def check_previous(previous, now):
    if previous is None:
        return
    if (not isinstance(previous, dict) or previous.get("schema_version") != 1 or
            previous.get("source") != "signalpilot_demo_reconciliation_guard_state"):
        raise ValueError("untrusted_previous_reconciliation")
    stamp = previous.get("last_observed_at")
    if type(stamp) is not int or stamp > now or stamp < 0:
        raise ValueError("invalid_previous_reconciliation_time")
    day = previous.get("last_day_utc")
    if not isinstance(day, str) or day != utc_day(stamp) or day > utc_day(now):
        raise ValueError("invalid_previous_reconciliation_day")
    for key in ("last_open_exposure", "prior_day_exposure_unresolved",
                "unattributed_history_unresolved", "observation_gap_unresolved"):
        if type(previous.get(key)) is not bool:
            raise ValueError("invalid_previous_reconciliation_flag")


def reconcile(pnl, attribution, account, exposure, previous=None, *, now=None):
    now = int(time.time()) if now is None else int(now)
    for data, source in (
        (pnl, "binance_demo_account_wide_income_read_only"),
        (attribution, "binance_demo_four_symbol_trade_attribution_read_only"),
        (account, "binance_demo_observation_only"),
        (exposure, "binance_demo_account_wide_unrealized_read_only"),
    ):
        check_observation(data, source, now)
    check_previous(previous, now)
    midnight = int(datetime.fromtimestamp(now, timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    if pnl.get("day_start_utc_ms") != midnight or attribution.get("day_start_utc_ms") != midnight:
        raise ValueError("income_and_fills_day_mismatch")
    if (attribution.get("status") != "AUDIT_ONLY_NOT_EXECUTABLE" or
            attribution.get("allocation_ledger_reconciled") is not False or
            attribution.get("execution_authorized") is not False):
        raise ValueError("untrusted_trade_attribution")
    realized = amount(pnl.get("realized_pnl_usdt"))
    commissions = amount(pnl.get("commissions_usdt"))
    funding = amount(pnl.get("funding_usdt"))
    net = amount(pnl.get("net_income_usdt"))
    if realized + commissions + funding != net or commissions > 0:
        raise ValueError("inconsistent_income_totals")
    owned_realized = amount(attribution.get("signalpilot_realized_pnl_usdt"))
    owned_fees = amount(attribution.get("signalpilot_commissions_usdt"))
    owned_net = amount(attribution.get("signalpilot_net_before_funding_usdt"))
    if owned_fees < 0 or owned_realized - owned_fees != owned_net:
        raise ValueError("inconsistent_attributed_trade_totals")
    owned = attribution.get("signalpilot_fills")
    unknown = attribution.get("unattributed_fills")
    if any(type(x) is not int or x < 0 for x in (owned, unknown)):
        raise ValueError("invalid_fill_counts")
    if owned > 0 and attribution.get("registry_present") is not True:
        raise ValueError("missing_verified_order_registry")
    symbols = account.get("exposed_symbols")
    exposed = exposure.get("exposed_symbols")
    if (not isinstance(symbols, list) or not isinstance(exposed, list) or
            any(not isinstance(s, str) or not s for s in symbols + exposed) or
            len(symbols) != len(set(symbols)) or len(exposed) != len(set(exposed)) or
            sorted(symbols) != sorted(exposed) or
            exposure.get("open_position_count") != len(exposed)):
        raise ValueError("inconsistent_open_positions")
    orders = account.get("open_orders")
    algos = account.get("open_algo_orders")
    if (not isinstance(orders, dict) or not isinstance(algos, dict) or
            any(type(x) is not int or x < 0 for x in list(orders.values()) + list(algos.values()))):
        raise ValueError("inconsistent_open_orders")
    open_exposure = bool(symbols or any(orders.values()) or any(algos.values()))
    day = utc_day(now)
    day_changed = previous is not None and previous["last_day_utc"] != day
    prior_day = ((previous["prior_day_exposure_unresolved"] or
                  (day_changed and previous["last_open_exposure"]))
                 if previous is not None else open_exposure)
    unmatched_history = ((previous["unattributed_history_unresolved"] if previous else False)
                         or unknown > 0)
    gap = ((previous["observation_gap_unresolved"] or
            now - previous["last_observed_at"] > MAX_GAP_SECONDS)
           if previous is not None else False)
    realized_gap = realized - owned_realized
    fee_gap = commissions + owned_fees
    reasons = []
    if prior_day:
        reasons.append("PRIOR_DAY_EXPOSURE_UNRECONCILED")
    if unmatched_history:
        reasons.append("UNATTRIBUTED_HISTORICAL_FILLS")
    if gap:
        reasons.append("MONITORING_GAP_UNRECONCILED")
    if realized_gap != 0 or fee_gap != 0:
        reasons.append("ACCOUNT_INCOME_DIFFERS_FROM_ATTRIBUTED_FILLS")
    if funding != 0:
        reasons.append("FUNDING_NOT_ATTRIBUTED_TO_STRATEGY")
    if open_exposure:
        reasons.append("OPEN_EXPOSURE_NOT_PROVEN_STRATEGY_OWNED")
    reasons.append("ACCOUNT_SCOPE_AND_VIRTUAL_ALLOCATION_NOT_RECONCILED")
    status = {
        "source": "signalpilot_demo_reconciliation_guard_read_only",
        "observed_at": now, "day_start_utc_ms": midnight,
        "account_realized_gap_usdt": str(realized_gap),
        "account_commission_gap_usdt": str(fee_gap),
        "account_funding_unattributed_usdt": str(funding),
        "unattributed_fills_today": unknown,
        "unattributed_history_unresolved": unmatched_history,
        "prior_day_exposure_unresolved": prior_day,
        "monitoring_gap_unresolved": gap,
        "open_exposure_now": open_exposure,
        "block_reasons": reasons,
        "reconciliation_requirements": {
            "historical_fills_resolved": not unmatched_history,
            "prior_day_exposure_resolved": not prior_day,
            "monitoring_continuous": not gap,
            "income_and_fees_matched": realized_gap == 0 and fee_gap == 0,
            "funding_attributed": funding == 0,
            "account_flat": not open_exposure,
            "account_wide_scope_verified": False,
            "virtual_allocation_enforced": False,
        },
        "status": "BLOCKED_UNRECONCILED",
        "allocation_ledger_reconciled": False,
        "risk_snapshot_approved": False,
        "execution_authorized": False, "orders_sent": False,
    }
    state = {
        "schema_version": 1, "source": "signalpilot_demo_reconciliation_guard_state",
        "last_observed_at": now, "last_day_utc": day,
        "last_open_exposure": open_exposure,
        "prior_day_exposure_unresolved": prior_day,
        "unattributed_history_unresolved": unmatched_history,
        "observation_gap_unresolved": gap,
    }
    return status, state


def run(root=ROOT, *, now=None):
    root = Path(root)
    now = int(time.time()) if now is None else int(now)
    try:
        pnl = trusted_json(root, "demo-pnl-observation.json")
        attr = trusted_json(root, "demo-trade-attribution.json")
        account = trusted_json(root, "demo-account-observation.json")
        exposure = trusted_json(root, "demo-exposure-observation.json")
        state_path = root / STATE
        previous = trusted_json(root, STATE) if state_path.exists() or state_path.is_symlink() else None
        status, state = reconcile(pnl, attr, account, exposure, previous, now=now)
        save_observation(state, state_path)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        status = {
            "source": "signalpilot_demo_reconciliation_guard_read_only",
            "observed_at": now, "status": "BLOCKED_INVALID_OR_STALE_INPUT",
            "error_type": type(exc).__name__,
            "allocation_ledger_reconciled": False,
            "risk_snapshot_approved": False,
            "execution_authorized": False, "orders_sent": False,
        }
    save_observation(status, root / OUTPUT)
    print(json.dumps(status, sort_keys=True))
    return status


if __name__ == "__main__":
    run()
