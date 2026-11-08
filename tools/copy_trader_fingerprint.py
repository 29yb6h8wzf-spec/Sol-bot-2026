"""Analyze publicly exported closed copy-trader positions (research only).

Usage: python tools/copy_trader_fingerprint.py history.csv
CSV fields: symbol,side,entryPrice,closePrice,openedAt,closedAt
Optional: leverage,roi,margin. Timestamps are Unix milliseconds or ISO-8601.
No orders, credentials or external requests.
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median


def timestamp(value):
    value = str(value).strip()
    if value.replace(".", "", 1).isdigit():
        seconds = float(value)
        return seconds / 1000 if seconds > 10**11 else seconds
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def analyze(rows):
    trades = []
    for n, row in enumerate(rows, 2):
        try:
            side = str(row["side"]).strip().upper()
            if side not in ("LONG", "SHORT", "BUY", "SELL"):
                raise ValueError("invalid side")
            direction = 1 if side in ("LONG", "BUY") else -1
            entry = float(row["entryPrice"])
            close = float(row["closePrice"])
            start = timestamp(row["openedAt"])
            end = timestamp(row["closedAt"])
            if entry <= 0 or close <= 0 or end < start:
                raise ValueError("invalid price or duration")
            pnl = direction * (close / entry - 1)
            trades.append({"symbol": str(row["symbol"]), "side": side,
                           "return_on_notional": pnl,
                           "duration_minutes": (end - start) / 60,
                           "start": start, "end": end})
        except (KeyError, ValueError, TypeError, OverflowError) as exc:
            raise ValueError(f"CSV row {n}: {exc}") from exc
    if not trades:
        raise ValueError("No closed trades supplied")
    wins = [t for t in trades if t["return_on_notional"] > 0]
    losses = [t for t in trades if t["return_on_notional"] < 0]
    avg_win = sum(t["return_on_notional"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["return_on_notional"] for t in losses) / len(losses) if losses else 0
    # Notional returns are NOT wallet equity returns; cannot infer portfolio MDD.
    return {
        "trade_count": len(trades),
        "win_rate": len(wins) / len(trades),
        "avg_win_notional_pct": round(avg_win * 100, 4),
        "avg_loss_notional_pct": round(avg_loss * 100, 4),
        "mean_gross_notional_pct": round(sum(t["return_on_notional"] for t in trades) / len(trades) * 100, 4),
        "median_duration_minutes": round(median(t["duration_minutes"] for t in trades), 2),
        "pairs": dict(Counter(t["symbol"] for t in trades)),
        "directions": dict(Counter(t["side"] for t in trades)),
        "overlapping_position_pairs": sum(
            a["start"] < b["end"] and b["start"] < a["end"]
            for i, a in enumerate(trades) for b in trades[i+1:]
        ),
        "caveat": "Gross price returns only; fees, funding, slippage, capital allocation, unrealized PnL and MDD not identifiable from this CSV.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    args = parser.parse_args()
    with args.csv_path.open(newline="", encoding="utf-8-sig") as stream:
        result = analyze(csv.DictReader(stream))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
