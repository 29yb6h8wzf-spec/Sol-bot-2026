"""Offline safety regression for the Demo-only reservation gate."""
import copy
import sqlite3
import pytest

from demo_execution_gate import DemoGateBlocked, reserve, validate

NOW = 1794266000


def evidence():
    signal = {"signal_id": "s-demo-001", "timestamp": NOW - 5}
    verified = {
        "signal_id": "s-demo-001", "symbol": "SOL/USDT:USDT",
        "direction": "long", "score": 89, "source": "verified_85_score_engine",
        "verification": {"status": "RECALCULATED_RESEARCH_CANDIDATE",
                         "score_verified_independently": True,
                         "execution_authorized": False},
    }
    route = {"signal_id": "s-demo-001", "status": "DEMO_ELIGIBLE_NOT_SUBMITTED"}
    plan = {"signal_id": "s-demo-001", "symbol": "SOL/USDT:USDT",
            "side": "long", "status": "INDICATIVE_PLAN_ONLY_NOT_EXECUTABLE",
            "orders_sent": False, "entry": "100", "stop": "99",
            "target": "102", "quantity": "0.1"}
    account = {"endpoint": "https://demo-fapi.binance.com",
               "authenticated": True, "one_way": True,
               "observed_at": NOW - 1, "positions_count": 0,
               "orders_count": 0, "algo_orders_count": 0,
               "margin_type": "isolated", "leverage": 2,
               "wallet_usdt": "150", "available_usdt": "150",
               "realized_pnl_today_usdt": "0", "min_notional_usdt": "5"}
    return [signal, verified, route, plan, account]


def test_eligible_no_orders():
    intent = validate(*evidence(), now=NOW)
    assert intent["mode"] == "DEMO_ONLY"
    assert intent["orders_sent"] is False
    assert intent["notional"] == "10.0"


@pytest.mark.parametrize("index,key,value", [
    (0, "timestamp", NOW - 121),
    (0, "timestamp", NOW + 1),
    (1, "score", 70),
    (1, "source", "user_payload"),
    (1, "symbol", "BTC/USDT:USDT"),
    (1, "direction", "sideways"),
    (1, "verification", {}),
    (2, "status", "BLOCKED_UNVERIFIED"),
    (3, "status", "PLANNED_ONLY"),
    (3, "orders_sent", True),
    (3, "quantity", "0.001"),
    (3, "quantity", "1"),
    (3, "quantity", "NaN"),
    (3, "stop", "101"),
    (3, "target", "99"),
    (3, "symbol", "XRP/USDT:USDT"),
    (4, "endpoint", "https://fapi.binance.com"),
    (4, "authenticated", False),
    (4, "one_way", False),
    (4, "observed_at", NOW - 11),
    (4, "positions_count", 1),
    (4, "orders_count", 1),
    (4, "algo_orders_count", 1),
    (4, "margin_type", "cross"),
    (4, "leverage", 3),
    (4, "wallet_usdt", "0"),
    (4, "available_usdt", "0"),
    (4, "realized_pnl_today_usdt", "-8"),
    (4, "min_notional_usdt", "12"),
])
def test_fail_closed(index, key, value):
    args = evidence()
    args[index][key] = value
    with pytest.raises(DemoGateBlocked):
        validate(*args, now=NOW)


def test_short_direction():
    args = evidence()
    args[1]["direction"] = "short"
    args[3]["side"] = "short"
    args[3]["stop"] = "101"
    args[3]["target"] = "98"
    assert validate(*args, now=NOW)["direction"] == "short"


def test_exactly_once_reservation(tmp_path):
    db = tmp_path / "reservations.sqlite3"
    args = evidence()
    intent = reserve(db, *args, now=NOW)
    assert intent["orders_sent"] is False
    with pytest.raises(DemoGateBlocked, match="already_reserved"):
        reserve(db, *args, now=NOW)
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT state FROM demo_execution_reservations").fetchone() == ("RESERVED_NO_ORDERS",)


def test_missing_directory_is_blocked(tmp_path):
    with pytest.raises(DemoGateBlocked, match="journal_directory_missing"):
        reserve(tmp_path / "missing" / "x.db", *evidence(), now=NOW)


def test_no_broker_or_order_imports():
    import inspect
    import demo_execution_gate
    source = inspect.getsource(demo_execution_gate)
    assert "import ccxt" not in source
    assert "create_order(" not in source
    assert "fapiPrivatePost" not in source
