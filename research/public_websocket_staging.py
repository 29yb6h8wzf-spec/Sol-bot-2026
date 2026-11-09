"""Read-only public WebSocket staging. No credentials or order endpoints."""
import asyncio
import json
import os
import resource
import time
from collections import defaultdict

import websockets

DURATION_SECONDS = 720
STREAMS = {
    "binance_SOL": ("wss://fstream.binance.com/ws/solusdt@bookTicker", None),
    "binance_XRP": ("wss://fstream.binance.com/ws/xrpusdt@bookTicker", None),
    "bybit_SOL": ("wss://stream.bybit.com/v5/public/linear",
                  {"op": "subscribe", "args": ["orderbook.1.SOLUSDT"]}),
    "bybit_XRP": ("wss://stream.bybit.com/v5/public/linear",
                  {"op": "subscribe", "args": ["orderbook.1.XRPUSDT"]}),
    "okx_SOL": ("wss://ws.okx.com:8443/ws/v5/public",
                {"op": "subscribe", "args": [{"channel": "books5", "instId": "SOL-USDT-SWAP"}]}),
    "okx_XRP": ("wss://ws.okx.com:8443/ws/v5/public",
                {"op": "subscribe", "args": [{"channel": "books5", "instId": "XRP-USDT-SWAP"}]}),
}


def extract(name, data):
    if name.startswith("binance"):
        return float(data["b"]), float(data["a"])
    if name.startswith("bybit") and data.get("topic", "").startswith("orderbook."):
        book = data["data"]
        return float(book["b"][0][0]), float(book["a"][0][0])
    if name.startswith("okx") and data.get("arg", {}).get("channel") == "books5" and data.get("data"):
        book = data["data"][0]
        return float(book["bids"][0][0]), float(book["asks"][0][0])
    return None


async def watch(name, url, subscription, deadline, stats):
    backoff = 1.0
    while time.monotonic() < deadline:
        try:
            async with websockets.connect(url, open_timeout=8, close_timeout=3,
                                          ping_interval=20, ping_timeout=15,
                                          max_size=2**20) as ws:
                stats[name]["connections"] += 1
                if subscription:
                    await ws.send(json.dumps(subscription))
                backoff = 1.0
                while time.monotonic() < deadline:
                    remaining = deadline - time.monotonic()
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=min(30, remaining))
                    except TimeoutError:
                        if time.monotonic() >= deadline:
                            break
                        raise
                    data = json.loads(message)
                    book = extract(name, data)
                    if book is None:
                        continue
                    bid, ask = book
                    if not (0 < bid < ask):
                        stats[name]["invalid_books"] += 1
                        continue
                    stats[name]["valid_books"] += 1
                    stats[name]["last_bid"] = bid
                    stats[name]["last_ask"] = ask
                    stats[name]["last_received_monotonic"] = round(time.monotonic(), 3)
        except (OSError, TimeoutError, ValueError, KeyError, IndexError,
                websockets.exceptions.WebSocketException) as exc:
            stats[name]["errors"] += 1
            stats[name]["last_error"] = type(exc).__name__ + ": " + str(exc)[:120]
            await asyncio.sleep(min(backoff, max(0, deadline - time.monotonic())))
            backoff = min(30.0, backoff * 2)


async def main():
    started = time.monotonic()
    deadline = started + DURATION_SECONDS
    stats = defaultdict(lambda: {"connections": 0, "valid_books": 0,
                                 "invalid_books": 0, "errors": 0})
    await asyncio.gather(*(watch(name, url, sub, deadline, stats)
                           for name, (url, sub) in STREAMS.items()))
    report = {"duration_seconds": round(time.monotonic() - started, 2),
              "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              "streams": {name: dict(stats[name]) for name in STREAMS}}
    os.makedirs("staging-results", exist_ok=True)
    with open("staging-results/public-websocket-720s.json", "w", encoding="utf-8") as out:
        json.dump(report, out, indent=2)
    print(json.dumps(report, indent=2))
    missing = [name for name, item in report["streams"].items() if item["valid_books"] == 0]
    if missing:
        raise RuntimeError("No valid public websocket books for: " + ", ".join(missing))
    if report["duration_seconds"] < DURATION_SECONDS:
        raise RuntimeError("Staging stopped early")


if __name__ == "__main__":
    asyncio.run(main())
