"""Read-only REAL Binance Futures V2 replay smoke research, NOT OOS proof.

Usage: PYTHONPATH=. python -m signals_v2.public_smoke
Uses public /fapi/v1/klines, no API keys, no order endpoints.
This tiny, recent and overlapping window is a *connectivity/feasibility*
diagnostic. Never interpret results as profitability evidence.
"""
import hashlib
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from signals_v2.contracts import Candle, MarketSnapshot, DataRejected
from signals_v2.hybrid import candidates
from signals_v2.replay import replay

HOST = "https://fapi.binance.com"
PATH = "/fapi/v1/klines"


def fetch(symbol: str, interval: str, limit: int = 1000) -> list:
    if symbol not in ("SOLUSDT", "XRPUSDT") or interval not in ("1m", "5m"):
        raise ValueError("unsupported_public_feed")
    url = HOST + PATH + "?" + urlencode(
        {"symbol": symbol, "interval": interval, "limit": limit})
    with urlopen(Request(url, headers={"User-Agent": "SignalPilot-V2-research"}),
                 timeout=20) as response:
        if response.status != 200:
            raise RuntimeError("public_data_http_failure")
        rows = json.load(response)
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("empty_public_data")
    return rows


def convert(rows, duration: int) -> tuple[Candle, ...]:
    bars = []
    for row in rows:
        start = int(row[0])
        bars.append(Candle(start, *(float(v) for v in row[1:6]),
                           available_at_ms=start + duration))
    return tuple(bars)


def run_symbol(symbol: str) -> dict:
    raw_five, raw_one = fetch(symbol, "5m"), fetch(symbol, "1m")
    digest = hashlib.sha256(json.dumps(
        {"five": raw_five, "one": raw_one},
        separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    five = convert(raw_five, 300_000)
    one = convert(raw_one, 60_000)
    one_lookup = {b.open_ms: b for b in one}
    results = {"symbol": symbol, "source": HOST + PATH,
               "snapshot_sha256": digest, "five_rows": len(five),
               "one_rows": len(one), "eligible": 0, "abstentions": 0,
               "rejected": {}, "proposals": 0, "replayed": 0,
               "net_r_descriptive": 0.0, "exit_reasons": {},
               "status": "DIAGNOSTIC_ONLY_NOT_OOS"}
    for i in range(80, len(five)-48):
        end = five[i-1].open_ms + 300_000
        if end > one[-1].open_ms + 60_000:
            break
        if end < one[0].open_ms + 600_000:
            continue
        minute_bars = tuple(one_lookup.get(t) for t in
                            range(end - 600_000, end, 60_000))
        if any(b is None for b in minute_bars):
            results["rejected"]["missing_one_minute"] = (
                results["rejected"].get("missing_one_minute", 0) + 1)
            continue
        decision = end
        snap = MarketSnapshot(symbol, decision, five[i-80:i], minute_bars)
        try:
            proposals = candidates(snap)
            results["eligible"] += 1
        except DataRejected as exc:
            key = str(exc)
            results["rejected"][key] = results["rejected"].get(key, 0) + 1
            continue
        if not proposals:
            results["abstentions"] += 1
        for proposal in proposals:
            results["proposals"] += 1
            try:
                outcome = replay(proposal, five[i:i+48])
            except DataRejected as exc:
                key = "replay_" + str(exc)
                results["rejected"][key] = results["rejected"].get(key, 0) + 1
                continue
            results["replayed"] += 1
            results["net_r_descriptive"] += outcome.net_r
            results["exit_reasons"][outcome.exit_reason] = (
                results["exit_reasons"].get(outcome.exit_reason, 0) + 1)
    return results


def main():
    for symbol in ("SOLUSDT", "XRPUSDT"):
        print(json.dumps(run_symbol(symbol), sort_keys=True))


if __name__ == "__main__":
    main()
