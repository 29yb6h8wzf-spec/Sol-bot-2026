"""Regression tests for Demo new-epoch reconciliation baseline. No network."""
import json
import os
import pytest

from demo_epoch_baseline import EpochBlocked, capture, inspect, persist_once

NOW = 1794267500


def sample():
    snap = {"endpoint": "https://demo-fapi.binance.com",
            "authenticated": True, "one_way": True,
            "observed_at": NOW - 2, "positions_count": 0,
            "orders_count": 0, "algo_orders_count": 0,
            "margin_type": "isolated", "leverage": 2,
            "wallet_usdt": "4500", "available_usdt": "4500",
            "realized_pnl_today_usdt": "-0.01762774",
            "min_notional_usdt": "5"}
    sol = dict(snap)
    xrp = dict(snap)
    provenance = {"source": "binance_demo_order_provenance_read_only",
                  "observed_at": NOW - 4, "status": "AUDIT_ONLY_NOT_EXECUTABLE",
                  "total_fills": 4, "verified_signalpilot_fills": 0,
                  "unattributed_fills": 4,
                  "order_classifications": {"EXTERNAL_OR_UNTAGGED": 4},
                  "execution_authorized": False}
    reconciliation = {"source": "signalpilot_demo_reconciliation_guard_read_only",
                      "observed_at": NOW - 4, "status": "BLOCKED_UNRECONCILED",
                      "unattributed_fills_today": 4,
                      "prior_day_exposure_unresolved": False,
                      "monitoring_gap_unresolved": False,
                      "open_exposure_now": False,
                      "unattributed_history_unresolved": True,
                      "account_realized_gap_usdt": "0",
                      "account_commission_gap_usdt": "-0.01762774",
                      "account_funding_unattributed_usdt": "0",
                      "day_start_utc_ms": 1794182400000,
                      "execution_authorized": False}
    risk = {"observed_at": NOW - 4, "status": "BLOCKED",
            "reason": "UNATTRIBUTED_DEMO_FILLS",
            "account_wide_net_usdt": "-0.01762774",
            "account_wide_realized_net_usdt": "-0.01762774",
            "allocation_ledger_reconciled": False,
            "execution_authorized": False}
    return [sol, xrp, provenance, reconciliation, risk]


def test_baseline_preserves_legacy_unknowns_and_daily_loss():
    epoch = capture(*sample(), now=NOW)
    assert epoch["legacy_audit"]["fill_count"] == 4
    assert epoch["legacy_audit"]["classification"] == "UNATTRIBUTED_PRE_EPOCH_NOT_SIGNALPILOT"
    assert epoch["account_day_pnl_at_start_usdt"] == "-0.01762774"
    assert epoch["effective_capital_usdt"] == "150"
    assert inspect(epoch)["baseline_integrity"] == "VERIFIED"
    assert epoch["execution_authorized"] is False


@pytest.mark.parametrize("index,key,value", [
    (0, "positions_count", 1),
    (0, "orders_count", 1),
    (1, "algo_orders_count", 1),
    (0, "endpoint", "https://fapi.binance.com"),
    (0, "authenticated", False),
    (0, "leverage", 3),
    (1, "margin_type", "cross"),
    (1, "wallet_usdt", "4400"),
    (0, "realized_pnl_today_usdt", "-8"),
    (0, "observed_at", NOW - 11),
    (2, "unattributed_fills", 0),
    (2, "execution_authorized", True),
    (3, "prior_day_exposure_unresolved", True),
    (3, "monitoring_gap_unresolved", True),
    (3, "open_exposure_now", True),
    (4, "reason", "DAILY_LOSS_KILL_SWITCH"),
    (4, "account_wide_net_usdt", "-8"),
    (4, "account_wide_realized_net_usdt", "0"),
])
def test_rejects_unsafe_baseline(index, key, value):
    args = sample()
    args[index][key] = value
    with pytest.raises(EpochBlocked):
        capture(*args, now=NOW)


def test_write_once_and_integrity(tmp_path):
    epoch = capture(*sample(), now=NOW)
    path = tmp_path / "demo-epoch.json"
    persist_once(path, epoch)
    assert os.stat(path).st_mode & 0o077 == 0
    assert inspect(json.loads(path.read_text()))["legacy_fill_count"] == 4
    with pytest.raises(FileExistsError):
        persist_once(path, epoch)
    tampered = json.loads(path.read_text())
    tampered["execution_authorized"] = True
    with pytest.raises(EpochBlocked, match="integrity"):
        inspect(tampered)


def test_no_exchange_or_order_imports():
    import inspect as pyinspect
    import demo_epoch_baseline
    source = pyinspect.getsource(demo_epoch_baseline)
    assert "import ccxt" not in source
    assert "create_order(" not in source
    assert "fapiPrivatePost" not in source
