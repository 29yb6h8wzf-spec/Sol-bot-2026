"""Authenticated Binance USDT-M DEMO-only account snapshot (GET requests only).

This is a read-only building block for a future Demo executor. It does not
send orders, modify account settings, or authorize trading.
"""
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlsplit

DEMO_HOST = "demo-fapi.binance.com"
INCOME_TYPES = frozenset({"REALIZED_PNL", "COMMISSION", "FUNDING_FEE", "INSURANCE_CLEAR"})


class DemoSnapshotError(RuntimeError):
    pass


def install_get_only_guard(exchange):
    urls = exchange.urls.get("api")
    if not isinstance(urls, dict):
        raise DemoSnapshotError("api_urls_missing")
    futures = [(key, value) for key, value in urls.items() if key.lower().startswith("fapi")]
    if not futures:
        raise DemoSnapshotError("futures_api_urls_missing")
    for key, url in futures:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != DEMO_HOST or parsed.port:
            raise DemoSnapshotError("non_demo_futures_url")
        if not parsed.path.startswith("/fapi/"):
            raise DemoSnapshotError("invalid_futures_api_path")
    original_fetch = exchange.fetch

    def guarded_fetch(url, method="GET", headers=None, body=None):
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname != DEMO_HOST
                or parsed.port or not parsed.path.startswith("/fapi/")
                or method.upper() != "GET"):
            raise DemoSnapshotError("non_demo_or_mutating_request_blocked")
        return original_fetch(url, method, headers, body)

    exchange.fetch = guarded_fetch
    exchange._signalpilot_get_only_guard = True
    return exchange


def demo_client_from_aws():
    """Retrieve credentials in process; never print or persist them."""
    import boto3
    import ccxt
    raw = boto3.client("secretsmanager", region_name="il-central-1").get_secret_value(
        SecretId="Demobinance")["SecretString"]
    keys = json.loads(raw)
    ex = ccxt.binanceusdm({"apiKey": keys["apiKey"], "secret": keys["secret"],
                           "enableRateLimit": True, "timeout": 15000})
    ex.enable_demo_trading(True)
    return install_get_only_guard(ex)


def _list(value, label):
    if not isinstance(value, list):
        raise DemoSnapshotError("invalid_" + label)
    return value


def _amount(value, label):
    try:
        result = Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        raise DemoSnapshotError("invalid_" + label) from None
    if not result.is_finite():
        raise DemoSnapshotError("invalid_" + label)
    return result


def read_snapshots(exchange, symbols=("SOLUSDT", "XRPUSDT"), *, now=None):
    """Read both symbols from ONE account-wide authenticated GET batch."""
    if (not isinstance(symbols, (tuple, list)) or not symbols
            or len(set(symbols)) != len(symbols)
            or any(s not in ("SOLUSDT", "XRPUSDT") for s in symbols)):
        raise DemoSnapshotError("unsupported_symbol")
    now = int(time.time()) if now is None else int(now)
    # The exchange must have a transport-level GET-only Demo guard installed.
    if not getattr(exchange, "_signalpilot_get_only_guard", False):
        raise DemoSnapshotError("guard_not_installed")
    account = exchange.fapiPrivateV3GetAccount()
    if not isinstance(account, dict):
        raise DemoSnapshotError("invalid_account")
    assets = [a for a in _list(account.get("assets"), "assets") if a.get("asset") == "USDT"]
    if len(assets) != 1:
        raise DemoSnapshotError("missing_usdt_asset")
    wallet = _amount(assets[0].get("walletBalance"), "wallet")
    available = _amount(assets[0].get("availableBalance"), "available")
    positions = _list(exchange.fapiPrivateV2GetPositionRisk(), "positions")
    if not positions:
        raise DemoSnapshotError("empty_position_inventory")
    active = sum(_amount(p.get("positionAmt"), "position_amt") != 0 for p in positions)
    orders = _list(exchange.fapiPrivateGetOpenOrders(), "orders")
    algos = exchange.fapiPrivateGetOpenAlgoOrders()
    if isinstance(algos, dict):
        algos = algos.get("orders")
    algos = _list(algos, "algos")
    mode = exchange.fapiPrivateGetPositionSideDual()
    if not isinstance(mode, dict) or str(mode.get("dualSidePosition")).lower() not in ("true", "false"):
        raise DemoSnapshotError("invalid_position_mode")
    info = exchange.fapiPublicGetExchangeInfo()
    if not isinstance(info, dict):
        raise DemoSnapshotError("invalid_exchange_info")
    # No pagination: fail closed if the full day cannot be proven complete.
    start_ms = int(datetime.fromtimestamp(now, timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    incomes = _list(exchange.fapiPrivateGetIncome({
        "startTime": start_ms, "endTime": now * 1000, "limit": 1000}), "income")
    if len(incomes) >= 1000:
        raise DemoSnapshotError("income_history_may_be_truncated")
    realized = Decimal("0")
    for item in incomes:
        if item.get("incomeType") in INCOME_TYPES:
            realized += _amount(item.get("income"), "income")
    # Record observation only AFTER all remote calls completed.
    observed_at = int(time.time())
    if abs(observed_at - now) > 10:
        raise DemoSnapshotError("account_snapshot_clock_skew")
    snapshots = {}
    markets = _list(info.get("symbols"), "markets")
    for symbol in symbols:
        matching = [p for p in positions if p.get("symbol") == symbol]
        if len(matching) != 1:
            raise DemoSnapshotError("symbol_position_inventory_missing")
        position = matching[0]
        selected = [s for s in markets if s.get("symbol") == symbol]
        if len(selected) != 1 or selected[0].get("status") != "TRADING":
            raise DemoSnapshotError("symbol_not_trading")
        filters = {f.get("filterType"): f for f in _list(selected[0].get("filters"), "filters")}
        if "MIN_NOTIONAL" not in filters:
            raise DemoSnapshotError("min_notional_missing")
        min_notional = _amount(filters["MIN_NOTIONAL"].get("notional"), "min_notional")
        if min_notional <= 0:
            raise DemoSnapshotError("invalid_min_notional")
        snapshots[symbol] = {
            "endpoint": "https://" + DEMO_HOST,
            "authenticated": True,
            "one_way": str(mode["dualSidePosition"]).lower() == "false",
            "observed_at": observed_at,
            "positions_count": active,
            "orders_count": len(orders),
            "algo_orders_count": len(algos),
            "margin_type": str(position.get("marginType", "")).lower(),
            "leverage": int(position.get("leverage", 0)),
            "wallet_usdt": str(wallet),
            "available_usdt": str(available),
            "realized_pnl_today_usdt": str(realized),
            "min_notional_usdt": str(min_notional),
        }
    return snapshots


def read_snapshot(exchange, symbol, *, now=None):
    return read_snapshots(exchange, (symbol,), now=now)[symbol]


def main():
    # Diagnostics are read-only. No sensitive values are printed.
    ex = demo_client_from_aws()
    for symbol in ("SOLUSDT", "XRPUSDT"):
        snapshot = read_snapshot(ex, symbol)
        print(json.dumps({"symbol": symbol, "demo": True,
                          "flat": snapshot["positions_count"] == 0,
                          "orders": snapshot["orders_count"],
                          "algos": snapshot["algo_orders_count"],
                          "one_way": snapshot["one_way"],
                          "isolated": snapshot["margin_type"] == "isolated",
                          "leverage_2x": snapshot["leverage"] == 2}))


if __name__ == "__main__":
    main()
