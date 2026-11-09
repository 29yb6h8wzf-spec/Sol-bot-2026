"""Paper-only replay from a locally supplied closed-candle JSON file.

Input schema: {"symbol":"SOLUSDT","signal_uid":"...","side":"LONG",
"quantity":"1","entry_mid":"100","stop":"98","target":"104",
"opened_at":1700000000,"bars":[{"open_ms":1700000000000,
"close_ms":1700000299999,"high":"105","low":"99","close":"104",
"confirmed_closed":true}]}
No network calls, no broker clients, no real orders.
"""
import argparse
import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from research.paper_closed_bar import ClosedBar, apply_closed_bar
from research.paper_order_store import DurablePaperOrders


def replay(payload: dict, database_path: str) -> dict:
    required = ("symbol", "signal_uid", "side", "quantity", "entry_mid",
                "stop", "target", "opened_at", "bars")
    if any(key not in payload for key in required):
        raise ValueError("missing replay input")
    if not isinstance(payload["bars"], list) or not payload["bars"]:
        raise ValueError("at least one candle required")
    store = DurablePaperOrders(database_path)
    uid = payload["signal_uid"]
    trade = store.open(uid, payload["side"], payload["quantity"],
                       payload["entry_mid"], payload["stop"], payload["target"],
                       int(payload["opened_at"]))
    processed = 0
    for item in payload["bars"]:
        bar = ClosedBar(
            open_ms=int(item["open_ms"]),
            close_ms=int(item["close_ms"]),
            high=Decimal(str(item["high"])),
            low=Decimal(str(item["low"])),
            close=Decimal(str(item["close"])),
            confirmed_closed=item["confirmed_closed"] is True,
        )
        trade = apply_closed_bar(store, uid, bar, bar.close_ms)
        processed += 1
        if trade.status != "OPEN":
            break
    return {"symbol": payload["symbol"], "bars_processed": processed,
            "trade": json.loads(json.dumps(asdict(trade), default=str))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--db", required=True)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    print(json.dumps(replay(payload, args.db), indent=2))


if __name__ == "__main__":
    main()
