"""Isolated public-market staging probe. No credentials, orders, or database writes."""
import json
import os
import resource
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

URLS = {
    "okx_SOL": "https://www.okx.com/api/v5/market/books?instId=SOL-USDT-SWAP&sz=5",
    "okx_XRP": "https://www.okx.com/api/v5/market/books?instId=XRP-USDT-SWAP&sz=5",
    "bybit_SOL": "https://api.bybit.com/v5/market/orderbook?category=linear&symbol=SOLUSDT&limit=5",
    "bybit_XRP": "https://api.bybit.com/v5/market/orderbook?category=linear&symbol=XRPUSDT&limit=5",
    "binance_SOL": "https://fapi.binance.com/fapi/v1/depth?symbol=SOLUSDT&limit=5",
    "binance_XRP": "https://fapi.binance.com/fapi/v1/depth?symbol=XRPUSDT&limit=5",
}
DURATION_SECONDS = 720
INTERVAL_SECONDS = 10
TIMEOUT_SECONDS = 4


def valid_book(name, payload):
    if name.startswith("okx"):
        data = payload["data"][0]
        bids, asks = data["bids"], data["asks"]
    elif name.startswith("bybit"):
        data = payload["result"]
        bids, asks = data["b"], data["a"]
    else:
        bids, asks = payload["bids"], payload["asks"]
    bid = float(bids[0][0])
    ask = float(asks[0][0])
    if not (0 < bid < ask):
        raise ValueError("invalid spread")
    return bid, ask


def run():
    started = time.monotonic()
    stats = defaultdict(lambda: {"success": 0, "failure": 0, "latencies_ms": [],
                                 "last_error": None, "last_bid": None, "last_ask": None})
    rounds = 0
    while time.monotonic() - started < DURATION_SECONDS:
        rounds += 1
        for name, url in URLS.items():
            tick = time.monotonic()
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "SignalPilot-Staging-ReadOnly/1.0"})
                with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                    payload = json.load(response)
                bid, ask = valid_book(name, payload)
                item = stats[name]
                item["success"] += 1
                item["last_bid"], item["last_ask"] = bid, ask
                item["latencies_ms"].append(round((time.monotonic() - tick) * 1000, 1))
            except (ValueError, KeyError, IndexError, TypeError, urllib.error.URLError,
                    TimeoutError, OSError, json.JSONDecodeError) as exc:
                item = stats[name]
                item["failure"] += 1
                item["last_error"] = type(exc).__name__ + ": " + str(exc)[:160]
        remaining = DURATION_SECONDS - (time.monotonic() - started)
        if remaining > 0:
            time.sleep(min(INTERVAL_SECONDS, remaining))
    elapsed = time.monotonic() - started
    report = {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "duration_seconds": round(elapsed, 2), "rounds": rounds,
              "rss_peak_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              "streams": dict(stats)}
    for item in report["streams"].values():
        latencies = item.pop("latencies_ms")
        item["latency_avg_ms"] = round(sum(latencies) / len(latencies), 1) if latencies else None
        item["latency_max_ms"] = max(latencies) if latencies else None
    os.makedirs("staging-results", exist_ok=True)
    with open("staging-results/public-market-720s.json", "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps(report, indent=2))
    if elapsed < DURATION_SECONDS:
        raise RuntimeError("staging duration too short")
    missing = [name for name in URLS if report["streams"].get(name, {}).get("success", 0) == 0]
    if missing:
        raise RuntimeError("public REST staging missing successful data for: " + ", ".join(missing))


if __name__ == "__main__":
    run()
