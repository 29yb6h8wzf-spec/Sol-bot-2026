"""Isolated Binance USDT-M DEMO bracket smoke test; never uses live endpoints.

Requires DEMO_TEST_CONFIRM=YES, a dedicated empty demo account, and manual
supervision. This is NOT certification for real-money trading.
"""
import json
import os
import sys
import time
from decimal import Decimal

import boto3
import ccxt

SYMBOL = "XRP/USDT:USDT"
CONFIRM = "YES"


def demo_exchange():
    raw = boto3.client("secretsmanager", region_name="il-central-1").get_secret_value(
        SecretId="Demobinance"
    )["SecretString"]
    keys = json.loads(raw)
    exchange = ccxt.binanceusdm({
        "apiKey": keys["apiKey"],
        "secret": keys["secret"],
        "enableRateLimit": True,
        "timeout": 20000,
    })
    exchange.enable_demo_trading(True)
    api_urls = str(exchange.urls["api"])
    if "demo-fapi.binance.com" not in api_urls or "fapi.binance.com" in api_urls.replace("demo-fapi.binance.com", ""):
        raise RuntimeError("Demo-only endpoint not verified")
    return exchange


def exposure(exchange):
    positions = exchange.fetch_positions([SYMBOL])
    return sum(
        (Decimal(str(p.get("contracts") or 0)) * (
            Decimal("-1") if p.get("side") == "short" else Decimal("1")
        ))
        for p in positions if p.get("symbol") == SYMBOL
    )


def algos(exchange):
    data = exchange.fapiPrivateGetOpenAlgoOrders({
        "symbol": exchange.market_id(SYMBOL)
    })
    if isinstance(data, dict):
        return data.get("orders", [])
    return data


def assert_demo(exchange):
    urls = str(exchange.urls["api"])
    if "demo-fapi.binance.com" not in urls:
        raise RuntimeError("Refusing non-demo exchange")


def cleanup(exchange):
    """Flatten first, verify flat, then remove protective orders.

    Never remove protection while exposure remains. If flatten fails,
    leave protective orders in place and require manual intervention.
    """
    assert_demo(exchange)
    last_error = None
    for attempt in range(3):
        try:
            qty = exposure(exchange)
            if qty > 0:
                exchange.create_order(
                    SYMBOL, "market", "sell", float(qty), None,
                    {"reduceOnly": True},
                )
            elif qty < 0:
                exchange.create_order(
                    SYMBOL, "market", "buy", float(-qty), None,
                    {"reduceOnly": True},
                )
            time.sleep(1)
            if exposure(exchange) == 0:
                break
        except Exception as exc:
            last_error = exc
            print("DEMO_FLATTEN_RETRY", attempt + 1, type(exc).__name__, flush=True)
            time.sleep(2)
    else:
        raise RuntimeError(
            "CRITICAL: demo position may remain open; protective orders NOT canceled. "
            "Inspect demo account manually."
        ) from last_error

    # Exposure is confirmed zero. Cancel stale protective orders only now.
    exchange.fapiPrivateDeleteAlgoOpenOrders({"symbol": exchange.market_id(SYMBOL)})
    exchange.cancel_all_orders(SYMBOL)
    if exposure(exchange) != 0 or exchange.fetch_open_orders(SYMBOL) or algos(exchange):
        raise RuntimeError("DEMO_CLEANUP_INCOMPLETE: inspect demo account manually")
    print("DEMO_CLEANUP_VERIFIED", flush=True)


def main():
    if os.getenv("DEMO_TEST_CONFIRM") != CONFIRM:
        print("PREPARED ONLY: DEMO_TEST_CONFIRM=YES required; no orders sent")
        return 0

    exchange = demo_exchange()
    assert_demo(exchange)
    exchange.load_markets()

    # Refuse a smoke test when any other strategy or manual trade owns demo exposure.
    positions = exchange.fetch_positions()
    if not isinstance(positions, list):
        raise RuntimeError("Demo account-wide position inventory invalid")
    for position in positions:
        amount = Decimal(str(position.get("contracts") or 0))
        if not amount.is_finite() or amount != 0:
            raise RuntimeError("Existing demo account-wide exposure; refusing test")
    exchange.options.setdefault("fetchOpenOrders", {})["warnWithoutSymbol"] = False
    orders = exchange.fetch_open_orders()
    if not isinstance(orders, list) or orders:
        raise RuntimeError("Existing or invalid demo account-wide ordinary orders; refusing test")
    algo_response = exchange.fapiPrivateGetOpenAlgoOrders({})
    if isinstance(algo_response, dict):
        if "orders" not in algo_response:
            raise RuntimeError("Invalid demo account-wide algo inventory")
        all_algos = algo_response["orders"]
    else:
        all_algos = algo_response
    if not isinstance(all_algos, list) or all_algos:
        raise RuntimeError("Existing or invalid demo account-wide algo orders; refusing test")
    if exposure(exchange) != 0 or exchange.fetch_open_orders(SYMBOL) or algos(exchange):
        raise RuntimeError("Existing demo XRP exposure/orders; refusing test")
    if exchange.fetch_position_mode(SYMBOL).get("hedged") is not False:
        raise RuntimeError("One-way mode required; account settings unchanged")

    exchange.set_leverage(2, SYMBOL)
    price = Decimal(str(exchange.fetch_ticker(SYMBOL)["last"]))
    if price <= 0:
        raise RuntimeError("Invalid demo price")
    qty = Decimal(str(exchange.amount_to_precision(
        SYMBOL, str(Decimal("10") / price)
    )))
    market = exchange.market(SYMBOL)
    min_qty = Decimal(str((market.get("limits", {}).get("amount") or {}).get("min") or 0))
    min_cost = Decimal(str((market.get("limits", {}).get("cost") or {}).get("min") or 0))
    if qty <= 0 or qty < min_qty or qty * price < min_cost or qty * price > 15:
        raise RuntimeError("Demo quantity outside permitted small range")

    stop = exchange.price_to_precision(SYMBOL, str(price * Decimal("0.985")))
    target = exchange.price_to_precision(SYMBOL, str(price * Decimal("1.015")))
    if not Decimal(stop) < price < Decimal(target):
        raise RuntimeError("Invalid bracket triggers")

    entry_may_exist = False
    try:
        assert_demo(exchange)
        entry_may_exist = True  # Treat network timeout as a possible fill.
        print("DEMO_ENTRY_SUBMITTING", flush=True)
        exchange.create_order(SYMBOL, "market", "buy", float(qty))
        actual = exposure(exchange)
        if actual <= 0:
            raise RuntimeError("Entry unconfirmed; recovery will check exposure")

        symbol_id = exchange.market_id(SYMBOL)

        def protect(order_type, trigger):
            assert_demo(exchange)
            return exchange.fapiPrivatePostAlgoOrder({
                "algoType": "CONDITIONAL",
                "symbol": symbol_id,
                "side": "SELL",
                "type": order_type,
                "triggerPrice": trigger,
                "closePosition": "true",
                "workingType": "MARK_PRICE",
            })

        stop_result = protect("STOP_MARKET", stop)
        target_result = protect("TAKE_PROFIT_MARKET", target)
        active = {str(o.get("algoId")) for o in algos(exchange)}
        if (str(stop_result.get("algoId")) not in active or
                str(target_result.get("algoId")) not in active):
            raise RuntimeError("Protective demo orders not verified")
        print("DEMO_BRACKET_VERIFIED", flush=True)
    finally:
        if entry_may_exist:
            try:
                cleanup(exchange)
            except Exception as exc:
                print(
                    "CRITICAL_DEMO_CLEANUP_FAILED: inspect demo XRP exposure and "
                    "orders immediately; DO NOT start live trading",
                    type(exc).__name__, flush=True,
                )
                raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
