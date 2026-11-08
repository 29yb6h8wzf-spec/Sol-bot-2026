"""Binance USDT-M LIVE connection preflight: read-only and fail-closed.

Does NOT submit orders, change leverage/margin, or enable live trading.
Supply BINANCE_LIVE_SECRET_ID only in a supervised environment with a dedicated
least-privilege secret. Never log keys or account balances.
"""
import json
import os
from decimal import Decimal


SYMBOLS = ("BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT")


def inspect(exchange):
    """Inspect existing positions, ordinary orders and conditional algo orders."""
    exchange.load_markets()
    urls = str(exchange.urls["api"])
    if "demo-fapi.binance.com" in urls or "testnet" in urls:
        raise ValueError("not_live_endpoint")
    if "fapi.binance.com" not in urls:
        raise ValueError("unverified_live_endpoint")
    if exchange.fetch_position_mode().get("hedged") is not False:
        raise ValueError("one_way_mode_required")
    positions = exchange.fetch_positions()  # Account-wide: reject exposure in ANY market.
    if not isinstance(positions, list):
        raise ValueError("invalid_account_wide_positions")
    exposure = []
    for p in positions:
        contracts = Decimal(str(p.get("contracts") or "0"))
        if not contracts.is_finite():
            raise ValueError("invalid_position_amount")
        if contracts != 0:
            exposure.append(p.get("symbol"))
    # Global ordinary order inventory: per-symbol checks alone miss other markets.
    global_orders = exchange.fetch_open_orders()
    if not isinstance(global_orders, list):
        raise ValueError("invalid_global_order_inventory")
    open_orders = {symbol: len(exchange.fetch_open_orders(symbol))
                   for symbol in SYMBOLS}
    algo_orders = {}
    for symbol in SYMBOLS:
        response = exchange.fapiPrivateGetOpenAlgoOrders({"symbol": exchange.market_id(symbol)})
        orders = response.get("orders", []) if isinstance(response, dict) else response
        algo_orders[symbol] = len(orders)
    if exposure or global_orders or any(open_orders.values()) or any(algo_orders.values()):
        raise ValueError("existing_exposure_or_orders_requires_manual_reconciliation")
    return {"status": "LIVE_CONNECTION_READ_ONLY_PARTIAL_SCOPE",
            "symbols_checked": list(SYMBOLS),
            "account_flat": True,
            "account_wide_algo_inventory_verified": False,
            "conditional_algo_endpoint_readable": True,
            "execution_authorized": False,
            "orders_sent": False}


def credential_pair(secret):
    """Accept known secret naming conventions without exposing any values."""
    if not isinstance(secret, dict):
        raise ValueError("invalid_secret_structure")
    for key_name, secret_name in (("apiKey", "secret"), ("Api", "Secret"), ("api_key", "api_secret"),
                                  ("API_KEY", "API_SECRET"), ("BINANCE_API_KEY", "BINANCE_API_SECRET")):
        key, token = secret.get(key_name), secret.get(secret_name)
        if isinstance(key, str) and key.strip() and isinstance(token, str) and token.strip():
            return key, token
    raise ValueError("unsupported_live_secret_schema")


def main():
    if os.getenv("LIVE_READONLY_PREFLIGHT") != "YES":
        print(json.dumps({"status": "DISABLED", "orders_sent": False}))
        return 0
    secret_id = os.getenv("BINANCE_LIVE_SECRET_ID")
    if not secret_id:
        raise SystemExit("BINANCE_LIVE_SECRET_ID required; no live API call made")
    import boto3
    import ccxt
    secret = json.loads(boto3.client("secretsmanager", region_name="il-central-1")
                        .get_secret_value(SecretId=secret_id)["SecretString"])
    api_key, api_secret = credential_pair(secret)
    exchange = ccxt.binanceusdm({"apiKey": api_key,
                                 "secret": api_secret,
                                 "enableRateLimit": True, "timeout": 20000})
    try:
        print(json.dumps(inspect(exchange)))
    finally:
        exchange.close() if hasattr(exchange, "close") else None


if __name__ == "__main__":
    main()
