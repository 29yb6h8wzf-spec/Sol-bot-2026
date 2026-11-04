import pytest
from demo_offline_fill_comparison import classify_fills


def fill(trade="1", order="10", client="external"):
    return {"symbol": "XRP/USDT:USDT", "trade_id": trade,
            "order_id": order, "client_order_id": client}


def test_no_registry_keeps_all_unattributed():
    result = classify_fills([fill("1"), fill("2", "10"), fill("3", "11")], {})
    assert result["total_fills"] == 3
    assert result["unique_orders"] == 2
    assert result["unattributed_fills"] == 3
    assert result["execution_authorized"] is False


def test_trusted_client_id_required():
    result = classify_fills([fill(client="expected")], {("XRP/USDT:USDT", "10"): "expected"})
    assert result["matched_fills"] == 1
    assert result["account_reconciled"] is False


def test_mismatched_client_id_is_unattributed():
    result = classify_fills([fill()], {("XRP/USDT:USDT", "10"): "expected"})
    assert result["unattributed_fills"] == 1


def test_duplicate_trade_fails_closed():
    with pytest.raises(ValueError, match="duplicate_fill"):
        classify_fills([fill(), fill()], {})


def test_missing_client_id_fails_closed():
    with pytest.raises(ValueError, match="missing_fill_identity"):
        classify_fills([{**fill(), "client_order_id": None}], {})
