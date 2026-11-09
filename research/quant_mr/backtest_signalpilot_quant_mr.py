"""Read-only historical SOL/XRP 15m VWAP research; NEVER sends an order.

Usage:
  python backtest_signalpilot_quant_mr.py --days 30 --save-snapshot candles.json
  python backtest_signalpilot_quant_mr.py --snapshot candles.json

This models next-bar-open hypothetical fills and mark-price STOP/TP triggers.
It is not forward Paper, not a live order, and not profitability validation.
Funding, liquidation, partial fills and market impact are not modeled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from signalpilot_quant_mr import (
    D, INTERVAL_MS, LEVERAGE, MARGIN_FRACTION, MAX_DAILY_WALLET_DRAWDOWN,
    SYMBOLS, WINDOW, SafetyError, decimal, floor_step, protection_prices,
    signal_from_closed_bars,
)

LOG = logging.getLogger("signalpilot.backtest")
TAKER_FEE = D("0.0005")  # configurable assumptions, NOT an account-specific fee quote
SLIPPAGE = D("0.0005")
MAX_ENTRY_GAP = D("0.005")
RESEARCH_RULES = {
    "SOL/USDT:USDT": (D("0.01"), D("0.01"), D("5")),
    "XRP/USDT:USDT": (D("0.1"), D("0.0001"), D("5")),
}


def _check_bars(rows, symbol, kind, asof_ms):
    if not isinstance(rows, list) or len(rows) < WINDOW + 2:
        raise SafetyError(f"Insufficient {kind} history for {symbol}")
    prev = None
    for row in rows:
        if not isinstance(row, list) or len(row) < 6:
            raise SafetyError(f"Malformed {kind} OHLCV for {symbol}")
        start = int(row[0])
        if start % INTERVAL_MS or (prev is not None and start != prev + INTERVAL_MS):
            raise SafetyError(f"Gap or duplicate in {kind} OHLCV for {symbol}")
        prev = start
        opening, high, low, close = map(decimal, (row[1], row[2], row[3], row[4]))
        if not 0 < low <= min(opening, close) <= max(opening, close) <= high:
            raise SafetyError(f"Invalid {kind} price for {symbol}")
        if kind == "trades" and decimal(row[5]) < 0:
            raise SafetyError(f"Invalid volume for {symbol}")
    if int(rows[-1][0]) + INTERVAL_MS > asof_ms:
        raise SafetyError(f"Unclosed {kind} candle for {symbol}")


def validate_snapshot(snapshot):
    if snapshot.get("schema") != "signalpilot-15m-market-mark-v1":
        raise SafetyError("Unrecognized historical snapshot schema")
    asof = int(snapshot["asof_ms"])
    for symbol in SYMBOLS:
        data = snapshot["symbols"][symbol]
        for kind in ("trades", "mark"):
            _check_bars(data[kind], symbol, kind, asof)
        if [r[0] for r in data["trades"]] != [r[0] for r in data["mark"]]:
            raise SafetyError(f"Unaligned mark/trade candles for {symbol}")
    if ([r[0] for r in snapshot["symbols"]["SOL/USDT:USDT"]["trades"]] !=
            [r[0] for r in snapshot["symbols"]["XRP/USDT:USDT"]["trades"]]):
        raise SafetyError("SOL/XRP historical windows do not align")
    return snapshot


def download_snapshot(days=30):
    """Public endpoints only. Fails closed if Binance is regionally blocked."""
    try:
        import ccxt
    except ImportError as exc:
        raise SafetyError("Install CCXT before downloading market data") from exc
    exchange = ccxt.binanceusdm({"enableRateLimit": True, "timeout": 20000})
    now_ms = int(time.time() * 1000)
    end_ms = (now_ms // INTERVAL_MS) * INTERVAL_MS
    start_ms = end_ms - int(days * 86400000)
    payload = {"schema": "signalpilot-15m-market-mark-v1", "asof_ms": end_ms,
               "source": "Binance USD-M public trade and mark klines",
               "symbols": {}}
    try:
        for symbol in SYMBOLS:
            result = {}
            for kind, params in (("trades", {}), ("mark", {"price": "mark"})):
                rows = []
                since = start_ms
                while since < end_ms:
                    chunk = exchange.fetch_ohlcv(symbol, "15m", since=since,
                                                limit=1500, params=params)
                    if not chunk:
                        raise SafetyError(f"No Binance {kind} data for {symbol}")
                    fresh = [r for r in chunk if since <= r[0] < end_ms]
                    if not fresh:
                        raise SafetyError("Binance history pagination did not advance")
                    rows.extend(fresh)
                    since = int(fresh[-1][0]) + INTERVAL_MS
                result[kind] = rows
                LOG.info("Downloaded %s %s candles for %s", len(rows), kind, symbol)
            payload["symbols"][symbol] = result
    finally:
        exchange.close()
    return validate_snapshot(payload)


def _fill(mid, side, opening):
    if opening:
        return mid * (1 + SLIPPAGE if side == "LONG" else 1 - SLIPPAGE)
    return mid * (1 - SLIPPAGE if side == "LONG" else 1 + SLIPPAGE)


def _equity(wallet, positions, marks):
    unrealized = sum((pos["qty"] * (marks[symbol] - pos["entry_fill"]) *
                      (1 if pos["side"] == "LONG" else -1))
                     for symbol, pos in positions.items())
    return wallet + unrealized


def simulate(snapshot, start_index, end_index):
    """Shared $150 portfolio, two positions max, one per symbol, no lookahead."""
    validate_snapshot(snapshot)
    data = snapshot["symbols"]
    length = len(data["SOL/USDT:USDT"]["trades"])
    if not WINDOW <= start_index < end_index <= length:
        raise SafetyError("Invalid chronological evaluation window")
    wallet = D("150")
    positions = {}
    pending = {}
    trades = []
    stats = defaultdict(int)
    day = None
    day_start = None
    peak_equity = D("150")
    max_drawdown = D(0)
    for index in range(start_index, end_index):
        candle_ms = int(data["SOL/USDT:USDT"]["trades"][index][0])
        utc_day = datetime.fromtimestamp(candle_ms / 1000, timezone.utc).date()
        if day != utc_day:
            day, day_start = utc_day, wallet
        marks_open = {s: decimal(data[s]["mark"][index][1]) for s in SYMBOLS}
        # Pending signal was recorded at the PREVIOUS candle close.
        # Enter only on the NEXT bar open; never fill on the signal bar.
        for symbol, side in list(pending.items()):
            del pending[symbol]
            if symbol in positions or len(positions) >= 2:
                stats["blocked_position"] += 1
                continue
            trade_bar = data[symbol]["trades"][index]
            prior_mark = decimal(data[symbol]["mark"][index - 1][4])
            mid = decimal(trade_bar[1])
            if abs(mid / prior_mark - 1) > MAX_ENTRY_GAP:
                stats["blocked_gap"] += 1
                continue
            if _equity(wallet, positions, marks_open) <= day_start * (
                    1 - MAX_DAILY_WALLET_DRAWDOWN):
                stats["blocked_daily_loss"] += 1
                continue
            step, tick, min_notional = RESEARCH_RULES[symbol]
            fill = _fill(mid, side, True)
            qty = floor_step(wallet * MARGIN_FRACTION * LEVERAGE / fill, step)
            if qty <= 0 or qty * mid < min_notional:
                stats["blocked_min_notional"] += 1
                continue
            # Actual wallet after taker fee can be slightly below prior wallet;
            # cap uses pre-order wallet, as in the execution layer.
            stop, take = protection_prices(fill, side, tick)
            fee = qty * fill * TAKER_FEE
            wallet -= fee
            positions[symbol] = {
                "side": side, "qty": qty, "entry_fill": fill,
                "stop": stop, "take": take, "entry_ms": candle_ms,
                "entry_fee": fee,
            }
            stats["entries"] += 1
        # Mark Price, not traded candle OHLC, triggers the simulated protection.
        for symbol, pos in list(positions.items()):
            mark_bar = data[symbol]["mark"][index]
            mark_open, high, low = map(decimal, (mark_bar[1], mark_bar[2], mark_bar[3]))
            long = pos["side"] == "LONG"
            hit_stop = low <= pos["stop"] if long else high >= pos["stop"]
            hit_take = high >= pos["take"] if long else low <= pos["take"]
            if not (hit_stop or hit_take):
                continue
            # Both touched in one candle -> STOP first (conservative).
            # Stop gaps fill at worse of trigger and mark open.
            trigger = ((min(mark_open, pos["stop"]) if long
                        else max(mark_open, pos["stop"])) if hit_stop
                       else pos["take"])
            exit_fill = _fill(trigger, pos["side"], False)
            gross = pos["qty"] * (exit_fill - pos["entry_fill"]) * (1 if long else -1)
            exit_fee = pos["qty"] * exit_fill * TAKER_FEE
            wallet += gross - exit_fee
            pnl = gross - exit_fee - pos["entry_fee"]
            trades.append({
                "symbol": symbol, "side": pos["side"],
                "entry_ms": pos["entry_ms"], "exit_ms": candle_ms + INTERVAL_MS,
                "quantity": str(pos["qty"]),
                "entry_fill": str(pos["entry_fill"]),
                "stop": str(pos["stop"]), "take": str(pos["take"]),
                "margin_allocated_usdt": str(pos["qty"] * pos["entry_fill"] / LEVERAGE),
                "status": "SL" if hit_stop else "TP", "net_pnl_usdt": str(pnl),
                "fees_usdt": str(pos["entry_fee"] + exit_fee),
            })
            del positions[symbol]
        marks_close = {s: decimal(data[s]["mark"][index][4]) for s in SYMBOLS}
        equity = _equity(wallet, positions, marks_close)
        peak_equity = max(peak_equity, equity)
        max_drawdown = max(max_drawdown, (peak_equity - equity) / peak_equity)
        # Signal is evaluated AFTER this 15m candle closes.
        for symbol in SYMBOLS:
            if symbol in positions or symbol in pending:
                continue
            series = data[symbol]["trades"]
            mark = decimal(data[symbol]["mark"][index][4])
            side, *_ = signal_from_closed_bars(series[index - WINDOW:index],
                                                series[index], mark)
            if side:
                stats["signals"] += 1
                if index + 1 < end_index:
                    pending[symbol] = side
                else:
                    stats["censored_signal_at_end"] += 1
    net = wallet - D("150")
    return {
        "label": "HISTORICAL_RESEARCH_ONLY_NOT_FORWARD_PAPER",
        "start_ms": data["SOL/USDT:USDT"]["trades"][start_index][0],
        "end_ms": data["SOL/USDT:USDT"]["trades"][end_index - 1][0],
        "starting_wallet_usdt": "150", "ending_wallet_usdt": str(wallet),
        "realized_net_usdt": str(net),
        "unrealized_pnl_usdt": str(_equity(wallet, positions, marks_close) - wallet),
        "max_equity_drawdown_fraction": str(max_drawdown),
        "open_positions_censored": list(positions),
        "counts": dict(stats),
        "closed_trades": len(trades),
        "wins": sum(decimal(t["net_pnl_usdt"]) > 0 for t in trades),
        "losses": sum(decimal(t["net_pnl_usdt"]) <= 0 for t in trades),
        "trades": trades,
        "assumptions": {
            "taker_fee_each_side": str(TAKER_FEE),
            "slippage_each_side": str(SLIPPAGE),
            "funding_included": False, "orders_sent": False,
            "stop_first_on_ambiguous_candle": True,
            "live_mark_price_reconstructed_by_mark_candle_close": True,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--snapshot", type=Path)
    source.add_argument("--days", type=int)
    parser.add_argument("--save-snapshot", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.snapshot:
        snapshot = validate_snapshot(json.loads(args.snapshot.read_text()))
    else:
        if not 1 <= args.days <= 180:
            parser.error("days must be between 1 and 180")
        snapshot = download_snapshot(args.days)
    raw = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode()).hexdigest()
    if args.save_snapshot:
        args.save_snapshot.write_text(json.dumps(snapshot, indent=2))
    n = len(snapshot["symbols"]["SOL/USDT:USDT"]["trades"])
    cut = max(WINDOW + 1, int(n * 0.7))
    report = {"snapshot_sha256": digest,
              "first_70pct": simulate(snapshot, WINDOW, cut),
              "last_30pct": simulate(snapshot, cut, n)}
    text = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(text)
    print(text)


if __name__ == "__main__":
    main()