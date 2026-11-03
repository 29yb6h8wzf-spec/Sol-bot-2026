"""Fail-closed, account-wide Binance DEMO risk monitor; read-only.

Reads the three existing observation files, records observed peak-to-trough
losses, and reports BLOCKED. It does NOT authorize trading or reconcile
SignalPilot's separate $150 allocation. Never sends orders.
"""
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

CAP = Decimal("7.50")
MAX_AGE_SECONDS = 90
ROOT = Path("/opt/signalpilot")


def number(value):
    try:
        x = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        raise ValueError("invalid_decimal") from None
    if not x.is_finite():
        raise ValueError("nonfinite_decimal")
    return x


def check_observation(data, source, now):
    if not isinstance(data, dict) or data.get("source") != source:
        raise ValueError("untrusted_observation_source")
    stamp = data.get("observed_at")
    if type(stamp) is not int or not 0 <= now - stamp <= MAX_AGE_SECONDS:
        raise ValueError("stale_observation")
    if data.get("orders_sent") is not False:
        raise ValueError("non_read_only_observation")


def assess(pnl, exposure, account, previous=None, *, now=None):
    now = int(time.time()) if now is None else int(now)
    day = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
    midnight = int(datetime.fromtimestamp(now, timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    state = {"day_utc": day, "peak_net_usdt": "0",
             "worst_drawdown_usdt": "0", "latched": False}
    if previous is not None:
        if not isinstance(previous, dict):
            raise ValueError("invalid_previous_state")
        prior_day = previous.get("day_utc")
        if type(prior_day) is not str or prior_day > day:
            raise ValueError("invalid_previous_day")
        if prior_day == day:
            state = dict(previous)
            if type(state.get("latched")) is not bool:
                raise ValueError("invalid_latch")
            if number(state.get("peak_net_usdt")) < 0 or number(state.get("worst_drawdown_usdt")) < 0:
                raise ValueError("invalid_previous_values")
    check_observation(pnl, "binance_demo_account_wide_income_read_only", now)
    check_observation(exposure, "binance_demo_account_wide_unrealized_read_only", now)
    check_observation(account, "binance_demo_observation_only", now)
    if pnl.get("day_start_utc_ms") != midnight:
        raise ValueError("pnl_day_mismatch")
    if any(x.get("allocation_ledger_reconciled") is True for x in (pnl, exposure)):
        raise ValueError("unexpected_allocation_claim")
    realized = number(pnl.get("net_income_usdt"))
    unrealized = number(exposure.get("unrealized_pnl_usdt"))
    net = realized + unrealized
    peak = max(Decimal("0"), number(state["peak_net_usdt"]), net)
    drawdown = peak - net
    worst = max(number(state["worst_drawdown_usdt"]), drawdown)
    latched = state["latched"] or worst >= CAP or net <= -CAP
    count = exposure.get("open_position_count")
    a_symbols = account.get("exposed_symbols")
    e_symbols = exposure.get("exposed_symbols")
    if type(count) is not int or count < 0:
        raise ValueError("invalid_position_count")
    if not isinstance(a_symbols, list) or not isinstance(e_symbols, list):
        raise ValueError("missing_position_symbols")
    if (any(type(s) is not str or not s for s in a_symbols + e_symbols)
            or len(a_symbols) != len(set(a_symbols))
            or len(e_symbols) != len(set(e_symbols))
            or count != len(e_symbols)
            or sorted(a_symbols) != sorted(e_symbols)):
        raise ValueError("exposure_observations_disagree")
    orders = account.get("open_orders")
    algos = account.get("open_algo_orders")
    if not isinstance(orders, dict) or not isinstance(algos, dict):
        raise ValueError("missing_order_observation")
    if any(type(v) is not int or v < 0 for v in list(orders.values()) + list(algos.values())):
        raise ValueError("invalid_order_count")
    untracked = bool(count or any(orders.values()) or any(algos.values()))
    next_state = {"day_utc": day, "peak_net_usdt": str(peak),
                  "worst_drawdown_usdt": str(worst), "latched": latched}
    reason = ("DAILY_LOSS_KILL_SWITCH" if latched else
              "UNATTRIBUTED_ACCOUNT_EXPOSURE" if untracked else
              "ALLOCATION_LEDGER_NOT_RECONCILED")
    status = {"status": "BLOCKED", "reason": reason,
              "account_wide_net_usdt": str(net),
              "account_wide_realized_net_usdt": str(realized),
              "account_wide_unrealized_usdt": str(unrealized),
              "worst_observed_drawdown_usdt": str(worst),
              "daily_loss_limit_usdt": str(CAP),
              "allocation_ledger_reconciled": False,
              "execution_authorized": False, "orders_sent": False}
    return status, next_state


def atomic_write(path, obj):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=".risk-monitor-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(obj, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def run(root=ROOT):
    root = Path(root)
    status_path = root / "demo-risk-monitor-status.json"
    state_path = root / "demo-risk-monitor-state.json"
    try:
        pnl = json.loads((root / "demo-pnl-observation.json").read_text())
        exposure = json.loads((root / "demo-exposure-observation.json").read_text())
        account = json.loads((root / "demo-account-observation.json").read_text())
        attribution = json.loads((root / "demo-trade-attribution.json").read_text())
        check_observation(attribution,
                          "binance_demo_four_symbol_trade_attribution_read_only",
                          int(time.time()))
        if (attribution.get("allocation_ledger_reconciled") is not False or
                attribution.get("execution_authorized") is not False or
                type(attribution.get("unattributed_fills")) is not int or
                attribution["unattributed_fills"] < 0):
            raise ValueError("invalid_trade_attribution")
        allocation_path = root / "demo-virtual-allocation.json"
        allocation_stat = allocation_path.lstat()
        if (allocation_path.is_symlink() or not allocation_path.is_file() or
                allocation_stat.st_uid != 0 or allocation_stat.st_mode & 0o077):
            raise ValueError("untrusted_allocation_observation")
        allocation = json.loads(allocation_path.read_text(encoding="utf-8"))
        check_observation(allocation,
                          "signalpilot_demo_virtual_allocation_read_only",
                          int(time.time()))
        if (allocation.get("status") != "BLOCKED_OBSERVATION_ONLY" or
                allocation.get("virtual_start_capital_usdt") != "150" or
                allocation.get("max_daily_loss_usdt") != "7.50" or
                allocation.get("execution_authorized") is not False or
                allocation.get("allocation_ledger_reconciled") is not False or
                allocation.get("unattributed_fills_today") != attribution["unattributed_fills"] or
                allocation.get("day_start_utc_ms") != attribution.get("day_start_utc_ms")):
            raise ValueError("invalid_virtual_allocation")
        stress_path = root / "demo-position-stress.json"
        stress_stat = stress_path.lstat()
        if (stress_path.is_symlink() or not stress_path.is_file() or
                stress_stat.st_uid != 0 or stress_stat.st_mode & 0o077):
            raise ValueError("untrusted_position_stress")
        stress = json.loads(stress_path.read_text(encoding="utf-8"))
        check_observation(stress, "binance_demo_position_stress_read_only", int(time.time()))
        if (stress.get("execution_authorized") is not False or
                stress.get("position_count") != exposure.get("open_position_count") or
                number(stress.get("unrealized_pnl_usdt")) != number(exposure.get("unrealized_pnl_usdt")) or
                number(stress.get("gross_notional_usdt")) < 0 or
                number(stress.get("stress_loss_2pct_usdt")) < 0 or
                number(stress.get("stress_loss_5pct_usdt")) < 0 or
                type(stress.get("stress_5pct_exceeds_daily_cap")) is not bool or
                type(stress.get("stress_2pct_exceeds_daily_cap")) is not bool):
            raise ValueError("invalid_position_stress")
        previous = json.loads(state_path.read_text()) if state_path.exists() else None
        status, state = assess(pnl, exposure, account, previous)
        if (attribution["unattributed_fills"] > 0 and
                status["reason"] != "DAILY_LOSS_KILL_SWITCH"):
            status["reason"] = "UNATTRIBUTED_DEMO_FILLS"
        if (stress["stress_2pct_exceeds_daily_cap"] and
                status["reason"] != "DAILY_LOSS_KILL_SWITCH"):
            status["reason"] = "POSITION_STRESS_EXCEEDS_DAILY_CAP"
        status["stress_loss_2pct_usdt"] = stress["stress_loss_2pct_usdt"]
        status["stress_loss_5pct_usdt"] = stress["stress_loss_5pct_usdt"]
        status["unattributed_fills"] = attribution["unattributed_fills"]
        status["virtual_allocation_usdt"] = allocation["virtual_start_capital_usdt"]
        status["virtual_allocation_reconciled"] = False
        atomic_write(state_path, state)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        status = {"status": "BLOCKED", "reason": "MISSING_OR_INVALID_OBSERVATION",
                  "error_type": type(exc).__name__,
                  "allocation_ledger_reconciled": False,
                  "execution_authorized": False, "orders_sent": False}
    status["observed_at"] = int(time.time())
    atomic_write(status_path, status)
    print(json.dumps(status, sort_keys=True))
    return status


if __name__ == "__main__":
    run()
