"""Read-only $150 *virtual* SignalPilot Demo allocation report.

Never transfers funds or segregates the Binance Demo account. Only verified
SignalPilot fills are included in the illustrative balance. Funding, other
symbols, pre-existing positions and unidentified fills prevent reconciliation.
No risk authorization, no trading, no creation of an approved account snapshot.
"""
import json
import os
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from demo_account_observer import save_observation
from demo_risk_monitor import check_observation

ROOT = Path("/opt/signalpilot")
OUTPUT = ROOT / "demo-virtual-allocation.json"
CAPITAL = Decimal("150")
MAX_LEVERAGE = 2
PER_TRADE_RISK = Decimal("1.50")
DAILY_LOSS_CAP = Decimal("7.50")


def money(raw):
    try:
        value = Decimal(str(raw))
    except (TypeError, ValueError, InvalidOperation):
        raise ValueError("invalid_allocation_amount") from None
    if not value.is_finite():
        raise ValueError("nonfinite_allocation_amount")
    return value


def compute(attribution, account, exposure, *, now=None):
    now = int(time.time()) if now is None else int(now)
    midnight = int(datetime.fromtimestamp(now, timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    check_observation(attribution, "binance_demo_four_symbol_trade_attribution_read_only", now)
    check_observation(account, "binance_demo_observation_only", now)
    check_observation(exposure, "binance_demo_account_wide_unrealized_read_only", now)
    if attribution.get("day_start_utc_ms") != midnight:
        raise ValueError("allocation_day_mismatch")
    if (attribution.get("status") != "AUDIT_ONLY_NOT_EXECUTABLE" or
            attribution.get("allocation_ledger_reconciled") is not False or
            attribution.get("execution_authorized") is not False):
        raise ValueError("invalid_attribution_provenance")
    realized = money(attribution.get("signalpilot_realized_pnl_usdt"))
    fees = money(attribution.get("signalpilot_commissions_usdt"))
    net = money(attribution.get("signalpilot_net_before_funding_usdt"))
    if fees < 0 or realized - fees != net:
        raise ValueError("attribution_accounting_mismatch")
    count = attribution.get("signalpilot_fills")
    unknown = attribution.get("unattributed_fills")
    if any(type(v) is not int or v < 0 for v in (count, unknown)):
        raise ValueError("invalid_fill_counts")
    if count > 0 and attribution.get("registry_present") is not True:
        raise ValueError("fills_without_registry")
    exposed = account.get("exposed_symbols")
    exposure_symbols = exposure.get("exposed_symbols")
    if (not isinstance(exposed, list) or not isinstance(exposure_symbols, list)
            or any(not isinstance(x, str) for x in exposed + exposure_symbols)
            or sorted(exposed) != sorted(exposure_symbols)
            or exposure.get("open_position_count") != len(exposure_symbols)):
        raise ValueError("inconsistent_positions")
    orders = account.get("open_orders")
    algos = account.get("open_algo_orders")
    if not isinstance(orders, dict) or not isinstance(algos, dict):
        raise ValueError("missing_open_order_data")
    if any(type(v) is not int or v < 0 for v in list(orders.values()) + list(algos.values())):
        raise ValueError("invalid_open_order_counts")
    total = money(account.get("usdt_total"))
    free = money(account.get("usdt_free"))
    if total < 0 or free < 0:
        raise ValueError("invalid_demo_balance")
    unallocated = bool(unknown or exposed or any(orders.values()) or any(algos.values()))
    balance = CAPITAL + net
    if balance < 0:
        raise ValueError("negative_virtual_allocation")
    reasons = ["FUNDING_NOT_ATTRIBUTED",
               "FOUR_SYMBOL_SCOPE_NOT_WHOLE_ACCOUNT",
               "VIRTUAL_ALLOCATION_NOT_EXCHANGE_SEGREGATED"]
    if unknown:
        reasons.append("UNATTRIBUTED_FILLS")
    if exposed:
        reasons.append("OPEN_POSITION_OWNERSHIP_UNVERIFIED")
    if any(orders.values()) or any(algos.values()):
        reasons.append("OPEN_ORDER_OWNERSHIP_UNVERIFIED")
    if total < CAPITAL:
        reasons.append("DEMO_ACCOUNT_BALANCE_BELOW_ALLOCATION")
    return {
        "source": "signalpilot_demo_virtual_allocation_read_only",
        "observed_at": now,
        "day_start_utc_ms": midnight,
        "virtual_start_capital_usdt": str(CAPITAL),
        "verified_signalpilot_fills_today": count,
        "unattributed_fills_today": unknown,
        "verified_realized_pnl_usdt": str(realized),
        "verified_commissions_usdt": str(fees),
        "indicative_net_before_funding_usdt": str(net),
        "indicative_virtual_balance_before_funding_usdt": str(balance),
        "max_trade_risk_usdt": str(PER_TRADE_RISK),
        "max_daily_loss_usdt": str(DAILY_LOSS_CAP),
        "max_leverage": MAX_LEVERAGE,
        "max_notional_usdt": str(CAPITAL * MAX_LEVERAGE),
        "open_position_count": len(exposed),
        "has_unattributed_account_activity": unallocated,
        "block_reasons": reasons,
        "status": "BLOCKED_OBSERVATION_ONLY",
        "allocation_ledger_reconciled": False,
        "risk_snapshot_approved": False,
        "execution_authorized": False,
        "orders_sent": False,
    }


def trusted_json(root, name):
    path = root / name
    st = path.lstat()
    if not path.is_file() or path.is_symlink() or st.st_uid != 0 or st.st_mode & 0o077:
        raise ValueError("untrusted_observation_file")
    return json.loads(path.read_text(encoding="utf-8"))


def run(root=ROOT):
    root = Path(root)
    try:
        attribution = trusted_json(root, "demo-trade-attribution.json")
        account = trusted_json(root, "demo-account-observation.json")
        exposure = trusted_json(root, "demo-exposure-observation.json")
        report = compute(attribution, account, exposure)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        report = {
            "source": "signalpilot_demo_virtual_allocation_read_only",
            "observed_at": int(time.time()),
            "status": "BLOCKED_INVALID_OR_STALE_INPUT",
            "error_type": type(exc).__name__,
            "allocation_ledger_reconciled": False,
            "risk_snapshot_approved": False,
            "execution_authorized": False,
            "orders_sent": False,
        }
    save_observation(report, root / "demo-virtual-allocation.json")
    print(json.dumps(report, sort_keys=True))
    return report


if __name__ == "__main__":
    run()
