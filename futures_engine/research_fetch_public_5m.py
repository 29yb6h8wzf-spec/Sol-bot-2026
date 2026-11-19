"""Read-only Binance USD-M 5m candle downloader for offline research.

Downloads public /fapi/v1/klines only. No credentials, order APIs, AWS or
production dependencies. Output is compatible with research_five_minute_score_replay_cli.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

FIVE_MS = 300_000
SYMBOLS = ("SOLUSDT", "XRPUSDT")
NAMES = {"SOLUSDT": "SOL/USDT:USDT", "XRPUSDT": "XRP/USDT:USDT"}
BASE = "https://fapi.binance.com/fapi/v1/klines"


def download(symbol, start_ms, cutoff_ms, *, opener=urlopen):
    if symbol not in SYMBOLS:
        raise ValueError("unsupported_symbol")
    if type(start_ms) is not int or type(cutoff_ms) is not int or (
        start_ms < 0 or start_ms % FIVE_MS or cutoff_ms % FIVE_MS or
        cutoff_ms <= start_ms
    ):
        raise ValueError("invalid_utc_range")
    result = []
    next_ms = start_ms
    while next_ms < cutoff_ms:
        query = urlencode({"symbol": symbol, "interval": "5m",
                           "startTime": next_ms, "endTime": cutoff_ms - 1,
                           "limit": 1500})
        with opener(BASE + "?" + query, timeout=20) as response:
            batch = json.load(response)
        if not isinstance(batch, list) or not batch:
            raise ValueError("missing_market_history")
        for raw in batch:
            if not isinstance(raw, list) or len(raw) < 6:
                raise ValueError("invalid_exchange_row")
            row = [int(raw[0]), *[float(x) for x in raw[1:6]]]
            if row[0] != next_ms:
                raise ValueError("market_history_gap_or_duplicate")
            if row[0] + FIVE_MS > cutoff_ms:
                raise ValueError("unclosed_market_candle")
            result.append(row)
            next_ms += FIVE_MS
        if len(batch) > 1500:
            raise ValueError("oversized_exchange_page")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-ms", type=int, required=True)
    parser.add_argument("--cutoff-ms", type=int, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    result = {NAMES[s]: download(s, args.start_ms, args.cutoff_ms)
              for s in SYMBOLS}
    with Path(args.output).open("x", encoding="utf-8") as f:
        json.dump(result, f, separators=(",", ":"))
        f.write("\n")
    print(json.dumps({"research_only": True, "rows": {
        k: len(v) for k, v in result.items()}}))


if __name__ == "__main__":
    main()
