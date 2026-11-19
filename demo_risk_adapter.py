"""Fail-closed demo risk adapter. Never submits orders.

Only accepts independently calculated bracket intents and a fresh trusted
account snapshot. Inbound Telegram/SQS payloads are never risk inputs.
"""
import json
import os
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

from futures_engine.order_preflight import check as order_check

CAPITAL_LIMIT = Decimal("150")
SNAPSHOT_PATH = "/opt/signalpilot/demo-risk-account.json"


def load_account(path=SNAPSHOT_PATH, *, now=None):
    now = int(time.time()) if now is None else int(now)
    file = Path(path)
    try:
        st = file.stat()
        if not file.is_file() or st.st_mode & 0o077:
            return None
        if st.st_uid != 0:
            return None
        data = json.loads(file.read_text(encoding="utf-8"))
        if data.get("source") != "binance_demo_read_only_verified":
            return None
        if type(data.get("observed_at")) is not int or not 0 <= now - data["observed_at"] <= 90:
            return None
        # Demo accounts may contain more than $150 in test funds; always cap
        # effective risk capital at the user's $150 sandbox allocation.
        equity = Decimal(str(data["equity"]))
        day_start = Decimal(str(data["day_start"]))
        used_margin = Decimal(str(data["used_margin"]))
        open_risk = Decimal(str(data["open_risk"]))
        if not all(v.is_finite() for v in (equity, day_start, used_margin, open_risk)):
            return None
        if not 0 < equity <= CAPITAL_LIMIT or not 0 < day_start <= CAPITAL_LIMIT:
            return None
        if used_margin < 0 or open_risk < 0:
            return None
        if data.get("leverage") != 2:
            return None
        return {"equity": str(equity), "day_start": str(day_start),
                "used_margin": str(used_margin), "open_risk": str(open_risk),
                "leverage": 2}
    except (OSError, KeyError, TypeError, ValueError, InvalidOperation):
        return None


def preflight(verified_intent, account):
    if not isinstance(verified_intent, dict) or not isinstance(account, dict):
        return False, "missing_trusted_risk_inputs"
    # Independent verifier only provides a signal, not bracket prices or qty.
    # Fail closed until a separate market-derived order planner supplies them.
    for key in ("entry", "stop", "target", "quantity"):
        if key not in verified_intent:
            return False, "independent_order_plan_missing"
    return order_check(verified_intent, account)


RISK_STATUS_PATH = "/opt/signalpilot/demo-risk-monitor-status.json"


def preflight_with_monitor(verified_intent, account, *,
                           status_path=RISK_STATUS_PATH, now=None):
    """Never approve a demo order while account allocation is unreconciled.

    The read-only monitor deliberately produces BLOCKED status only. A future
    separately tested reconciler must implement an approved risk snapshot.
    """
    now = int(time.time()) if now is None else int(now)
    try:
        file = Path(status_path)
        st = file.stat()
        if not file.is_file() or st.st_uid != 0 or st.st_mode & 0o077:
            return False, "risk_monitor_status_untrusted"
        status = json.loads(file.read_text(encoding="utf-8"))
        if type(status.get("observed_at")) is not int or not 0 <= now - status["observed_at"] <= 90:
            return False, "risk_monitor_status_stale"
        if (status.get("status") != "APPROVED" or
                status.get("allocation_ledger_reconciled") is not True or
                status.get("execution_authorized") is not True):
            return False, "risk_monitor_blocked"
        return preflight(verified_intent, account)
    except (OSError, ValueError, TypeError, KeyError):
        return False, "risk_monitor_status_missing"


EPOCH_BASELINE_PATH = "/opt/signalpilot/demo-epoch-baseline.json"
EPOCH_STATUS_PATH = "/opt/signalpilot/demo-epoch-risk-status.json"


def preflight_with_epoch(verified_intent, *, baseline_path=EPOCH_BASELINE_PATH,
                         status_path=EPOCH_STATUS_PATH, now=None):
    """Offline-only Demo risk check. Does not submit or authorize orders.

    Requires immutable root-owned baseline and fresh root-owned reconciled
    epoch status; never interprets historical UNKNOWN fills as owned.
    """
    from demo_epoch_baseline import inspect, amount
    now = int(time.time()) if now is None else int(now)
    try:
        baseline_file = Path(baseline_path)
        status_file = Path(status_path)
        for file in (baseline_file, status_file):
            st = file.lstat()
            if (file.is_symlink() or not file.is_file() or
                    st.st_uid != 0 or st.st_mode & 0o077):
                return False, "epoch_evidence_untrusted"
        baseline = json.loads(baseline_file.read_text(encoding="utf-8"))
        status = json.loads(status_file.read_text(encoding="utf-8"))
        inspect(baseline)
        if (status.get("source") != "signalpilot_demo_epoch_reconciler"
                or status.get("status") != "EPOCH_RISK_RECONCILED"
                or status.get("mode") != "DEMO_ONLY"
                or status.get("risk_preflight_eligible") is not True
                or status.get("allocation_ledger_reconciled") is not True
                or status.get("execution_authorized") is not False
                or status.get("orders_sent") is not False
                or status.get("baseline_sha256") != baseline["baseline_sha256"]
                or status.get("epoch_started_at") != baseline["epoch_started_at"]
                or status.get("post_epoch_unattributed_fills") != 0):
            return False, "epoch_risk_not_reconciled"
        stamp = status.get("observed_at")
        if type(stamp) is not int or not 0 <= now - stamp <= 10:
            return False, "epoch_risk_status_stale"
        if now // 86400 != baseline["epoch_started_at"] // 86400:
            return False, "epoch_rollover_requires_new_baseline"
        if amount(status.get("account_day_pnl_usdt")) <= Decimal("-7.50"):
            return False, "epoch_daily_loss_limit"
        account = {key: status[key] for key in
                   ("equity", "day_start", "used_margin", "open_risk", "leverage")}
        if account["leverage"] != 2 or amount(account["day_start"]) != Decimal("150"):
            return False, "epoch_capital_mismatch"
        if amount(account["equity"]) != min(
                Decimal("150"), Decimal("150") + amount(status["account_day_pnl_usdt"])):
            return False, "epoch_equity_mismatch"
        if amount(account["used_margin"]) != 0 or amount(account["open_risk"]) != 0:
            return False, "epoch_unexpected_open_risk"
        ok, reason = preflight(verified_intent, account)
        if not ok:
            return ok, reason
        entry = amount(verified_intent["entry"])
        qty = amount(verified_intent["quantity"])
        stop = amount(verified_intent["stop"])
        if qty * entry > Decimal("15"):
            return False, "epoch_margin_allocation_exceeded"
        if qty * (abs(entry - stop) + entry * Decimal("0.002")) > Decimal("1.50"):
            return False, "epoch_trade_risk_including_buffer_exceeded"
        return True, "demo_epoch_offline_preflight_only"
    except (OSError, KeyError, TypeError, ValueError, InvalidOperation):
        return False, "epoch_evidence_missing_or_invalid"
