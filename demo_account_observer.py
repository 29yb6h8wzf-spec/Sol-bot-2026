"""Read-only Binance USDT-M DEMO account observer.

Never creates/cancels orders, changes leverage, or authorizes execution.
Observation is deliberately NOT an approved risk snapshot: day-start equity,
realized PnL, funding and fees still require independently reconciled ledger.
"""
import json
import os
import tempfile
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

SYMBOLS = ("BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT")
OUTPUT = "/opt/signalpilot/demo-account-observation.json"


def demo_exchange():
    import boto3
    import ccxt
    raw = boto3.client("secretsmanager", region_name="il-central-1").get_secret_value(
        SecretId="Demobinance")["SecretString"]
    credentials = json.loads(raw)
    exchange = ccxt.binanceusdm({
        "apiKey": credentials["apiKey"],
        "secret": credentials["secret"],
        "enableRateLimit": True,
        "timeout": 20000,
    })
    exchange.enable_demo_trading(True)
    assert_demo(exchange)
    return exchange


def assert_demo(exchange):
    urls = str(exchange.urls["api"])
    if "demo-fapi.binance.com" not in urls or (
        "fapi.binance.com" in urls.replace("demo-fapi.binance.com", "")
    ):
        raise RuntimeError("non_demo_endpoint_blocked")


def number(value):
    d = Decimal(str(value))
    if not d.is_finite():
        raise ValueError("nonfinite_account_number")
    return d


def observe(exchange):
    assert_demo(exchange)
    exchange.load_markets()
    balance = exchange.fetch_balance()
    usdt = balance.get("USDT")
    if not isinstance(usdt, dict):
        raise ValueError("missing_usdt_balance")
    total = number(usdt["total"])
    free = number(usdt["free"])
    if total < 0 or free < 0:
        raise ValueError("negative_balance")
    positions = exchange.fetch_positions()
    exposed = []
    for position in positions:
        contracts = number(position.get("contracts") or 0)
        if contracts != 0:
            exposed.append(str(position.get("symbol")))
    open_orders = {}
    open_algos = {}
    for symbol in SYMBOLS:
        assert_demo(exchange)
        open_orders[symbol] = len(exchange.fetch_open_orders(symbol))
        response = exchange.fapiPrivateGetOpenAlgoOrders({
            "symbol": exchange.market_id(symbol)})
        orders = response.get("orders", []) if isinstance(response, dict) else response
        if not isinstance(orders, list):
            raise ValueError("invalid_algo_orders")
        open_algos[symbol] = len(orders)
    return {
        "source": "binance_demo_observation_only",
        "observed_at": int(time.time()),
        "usdt_total": str(total),
        "usdt_free": str(free),
        "exposed_symbols": sorted(exposed),
        "open_orders": open_orders,
        "open_algo_orders": open_algos,
        "risk_snapshot_approved": False,
        "orders_sent": False,
    }


def save_observation(observation, path=OUTPUT):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".demo-observation-", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(observation, f, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main():
    exchange = demo_exchange()
    try:
        result = observe(exchange)
        save_observation(result)
        print(json.dumps(result, sort_keys=True))
    finally:
        if hasattr(exchange, "close"):
            exchange.close()


if __name__ == "__main__":
    main()
