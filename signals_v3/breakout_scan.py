"""Inspect the historical V3 breakout decision using Binance USD-M public candles.

Run from the checkout with python -m signals_v3.breakout_scan.
This diagnostic evaluates the latest hourly decision considered by the replay.
Its output is a research observation. It must never be routed as an order.
"""
import json
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import urlopen

from signals_v2.contracts import Candle
from signals_v3.router import candidates

BASE = "https://fapi.binance.com"
FIVE = 300_000
HOUR = 12 * FIVE


def latest_decision(now_ms):
    now = datetime.fromtimestamp(now_ms / 1000, timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    first = int(start.timestamp()) * 1000 + 64 * FIVE
    if now_ms < first:
        return None
    return first + ((now_ms - first) // HOUR) * HOUR


def get_json(path):
    with urlopen(BASE + path, timeout=8) as response:
        return json.load(response)


def candles(symbol, interval, count, duration, decision):
    params = dict(symbol=symbol, interval=interval, limit=count, endTime=decision - 1)
    rows = get_json("/fapi/v1/klines?" + urlencode(params))
    expected = list(range(decision - duration * count, decision, duration))
    if [row[0] for row in rows] != expected:
        raise ValueError("missing_or_misaligned_candles")
    if any(row[6] != row[0] + duration - 1 for row in rows):
        raise ValueError("incorrect_candle_close")
    return tuple(Candle(row[0], *(float(v) for v in row[1:6]), row[6] + 1) for row in rows)


def scan(symbol, decision):
    five = candles(symbol, "5m", 64, FIVE, decision)
    one = candles(symbol, "1m", 45, 60_000, decision)
    proposals = candidates(symbol, five, one, decision)
    if not proposals:
        return {"status": "no_candidate"}
    first = proposals[0]
    if first.strategy != "volatility_breakout":
        return {"status": "other_strategy_first", "strategy": first.strategy}
    return {"status": "research_candidate", "direction": first.direction,
            "entry_reference": first.entry_reference, "stop_reference": first.stop_reference,
            "target_reference": first.target_reference}


def main():
    now_ms = int(get_json("/fapi/v1/time")["serverTime"])
    if abs(time.time_ns() // 1_000_000 - now_ms) > 30_000:
        raise ValueError("clock_disagreement")
    decision = latest_decision(now_ms)
    report = {"server_time_ms": now_ms, "decision_ms": decision, "research_only": True}
    if decision is None:
        report["status"] = "monthly_warmup"
    else:
        report["symbols"] = {s: scan(s, decision) for s in ("SOLUSDT", "XRPUSDT")}
    print(json.dumps(report, allow_nan=False))


if __name__ == "__main__":
    main()
