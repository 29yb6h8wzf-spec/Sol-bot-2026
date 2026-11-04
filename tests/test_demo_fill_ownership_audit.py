from demo_fill_ownership_audit import classify_fills
import pytest


def fill(order="100", trade="1"):
    return {"symbol": "XRP/USDT:USDT", "order_id": order, "trade_id": trade}


def test_unmatched_is_not_assumed_external():
    result = classify_fills([fill()], {})
    assert result["fills"][0]["category"] == "UNATTRIBUTED"
    assert result["execution_authorized"] is False


def test_verified_registry_receipt_is_attributed():
    receipt = {"symbol": "XRP/USDT:USDT", "order_id": "100",
               "client_order_id": "SPDEMO-verified"}
    result = classify_fills([fill()], {("XRP/USDT:USDT", "100"): receipt})
    assert result["counts"]["SIGNALPILOT_VERIFIED"] == 1
    assert result["orders_sent"] is False


def test_duplicate_trade_identity_is_rejected():
    with pytest.raises(ValueError, match="duplicate_trade_identity"):
        classify_fills([fill(), fill()], {})


def test_bad_registry_receipt_is_rejected():
    with pytest.raises(ValueError, match="inconsistent_registry_receipt"):
        classify_fills([fill()], {("XRP/USDT:USDT", "100"):
                                 {"symbol": "BTC/USDT:USDT", "order_id": "100"}})
