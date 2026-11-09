"""Audit historical 85+ scanner setups against subsequent CLOSED 5m candles.

This is an IN-SAMPLE, retrospective, fee/slippage-adjusted Paper simulation,
not forward Paper trading or proof of profitability. 30m maximum holding.
"""
import argparse
import json
import tempfile
from bisect import bisect_right
from collections import Counter
from decimal import Decimal
from pathlib import Path

from futures_engine.verified_strategy_scan import evaluate, to_strategy_candles
from research.paper_auto_replay import replay_saved_scan
from research.paper_rolling_filter_audit import rolling_filter_report


class _OfflineExchange:
    def close(self):
        pass


def _bar(row):
    return {
        "open_ms": row[0], "close_ms": row[0] + 299999,
        "open": row[1], "high": row[2], "low": row[3], "close": row[4],
        "confirmed_closed": True,
    }


def audit_historical_outcomes(five, four, *, symbol, asof_ms):
    rolling = rolling_filter_report(five, four, symbol=symbol, asof_ms=asof_ms)
    close_4h = [row[0] + 14400000 for row in four]
    five_times = {row[0]: index for index, row in enumerate(five)}
    outcomes = []
    next_allowed_ms = 0
    with tempfile.TemporaryDirectory(prefix="signalpilot-research-") as directory:
        for row in rolling["scans"]:
            if not row["setups_85_plus"]:
                continue
            candle_ms = row["candle_ms"]
            index = five_times[candle_ms]
            entry_ms = candle_ms + 300000
            for setup in row["setups_85_plus"]:
                record = {
                    "signal_candle_ms": candle_ms,
                    "strategy": setup["strategy"],
                    "direction": setup["direction"], "score": setup["score"],
                    "orders_sent": False,
                }
                if entry_ms < next_allowed_ms:
                    record["status"] = "SKIPPED_OVERLAP"
                    outcomes.append(record)
                    continue
                if len(five[index + 1:index + 7]) != 6:
                    record["status"] = "CENSORED_NO_FULL_30M_FUTURE"
                    outcomes.append(record)
                    continue
                n_four = bisect_right(close_4h, candle_ms + 300000)
                history_five = five[:index + 1]
                history_four = four[:n_four]

                def loader(requested_symbol, timeframe):
                    if requested_symbol != symbol:
                        raise ValueError("unexpected research symbol")
                    return _OfflineExchange(), {}, (
                        history_five if timeframe == "5m" else history_four
                    )

                scan = evaluate(symbol, loader=loader, now_ms=candle_ms + 300000)
                matches = [
                    i for i, candidate in enumerate(scan["candidates_85_plus"])
                    if all(candidate[k] == setup[k]
                           for k in ("strategy", "direction", "score"))
                ]
                if len(matches) != 1:
                    raise ValueError("historical candidate verification drift")
                bars = [_bar(five[index])]
                bars.extend(_bar(x) for x in five[index + 1:index + 7])
                db = str(Path(directory) / f"{index}-{len(outcomes)}.sqlite3")
                try:
                    replay = replay_saved_scan(
                        scan, bars, database_path=db,
                        candidate_index=matches[0],
                        five_history=to_strategy_candles(history_five),
                        four_history=to_strategy_candles(history_four),
                    )
                    trade = replay["trade"]
                    if trade["status"] == "OPEN":
                        raise ValueError("Paper trade remained open past 30m")
                    record.update({
                        "status": trade["status"],
                        "net_pnl_usd": trade["net_pnl"],
                        "estimated_risk_usd": replay["paper_plan"]["estimated_risk_usd"],
                        "quantity": replay["paper_plan"]["quantity"],
                        "bars_processed": replay["bars_processed"],
                    })
                    # Do not reuse a 5m bar for two Paper trades on this symbol.
                    next_allowed_ms = entry_ms + replay["bars_processed"] * 300000
                except ValueError as exc:
                    record.update({"status": "BLOCKED", "reason": str(exc)})
                outcomes.append(record)
    counts = Counter(o["status"] for o in outcomes)
    realized = [
        Decimal(o["net_pnl_usd"]) for o in outcomes if "net_pnl_usd" in o
    ]
    return {
        "status": "HISTORICAL_IN_SAMPLE_PAPER_AUDIT",
        "symbol": symbol, "orders_sent": False,
        "live_authorized": False, "out_of_sample": False,
        "profitability_validated": False, "funding_included": False,
        "exchange_rules": "PINNED_RESEARCH_2026-11-09",
        "holding_minutes": 30,
        "raw_candidates_85_plus": len(outcomes),
        "statuses": dict(sorted(counts.items())),
        "realized_simulated_net_pnl_usd": str(sum(realized, Decimal(0))),
        "evaluated_closed_trades": len(realized),
        "outcomes": outcomes,
    }


def main():
    parser = argparse.ArgumentParser(description="Offline historical 85+ Paper outcome audit")
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    items = payload.get("items")
    if items is None:
        items = [payload]
    for item in items:
        print(json.dumps(audit_historical_outcomes(
            item["five"], item["four"], symbol=item["symbol"],
            asof_ms=payload.get("captured_at_ms", item.get("asof_ms")),
        ), sort_keys=True))


if __name__ == "__main__":
    main()
