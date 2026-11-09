"""SignalPilot: SOL/XRP 15m VWAP mean reversion, Binance USD-M futures.

Default: read-only DRY_RUN. This has NOT been validated on a funded account.
Live trading is disabled unless explicitly armed via environment variables.
Binance conditional orders use the Algo Service, NOT the old order endpoint.
"""
from __future__ import annotations

import fcntl
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from pathlib import Path

try:
    import ccxt
except ModuleNotFoundError:  # offline unit tests; trading requires CCXT
    ccxt = None

CCXT_ERRORS = (ccxt.BaseError,) if ccxt is not None else ()

D = Decimal
LOG = logging.getLogger("signalpilot.mr")
SYMBOLS = {"SOL/USDT:USDT": "SOLUSDT", "XRP/USDT:USDT": "XRPUSDT"}
INTERVAL_MS = 15 * 60 * 1000
WINDOW = 20
LEVERAGE = 3
MARGIN_FRACTION = D("0.05")
STOP_FRACTION = D("0.015")
TAKE_FRACTION = D("0.03")
VOLUME_MULTIPLIER = D("1.5")
MAX_DAILY_WALLET_DRAWDOWN = D("0.05")
ALGO_PREFIX = "QMR_"
LIVE = os.getenv("SIGNALPILOT_MODE", "dry_run") == "live"
DB_PATH = Path(os.getenv("SIGNALPILOT_STATE_DB", "signalpilot_quant_mr.sqlite3"))


class SafetyError(RuntimeError):
    pass


def decimal(value) -> Decimal:
    result = D(str(value))
    if not result.is_finite():
        raise SafetyError("Non-finite numeric input")
    return result


def floor_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def round_tick(value: Decimal, tick: Decimal, rounding) -> Decimal:
    return (value / tick).to_integral_value(rounding=rounding) * tick


class State:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), isolation_level=None)
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.execute("CREATE TABLE IF NOT EXISTS seen (symbol TEXT, candle_ms INTEGER, "
                        "PRIMARY KEY(symbol, candle_ms))")
        self.db.execute("CREATE TABLE IF NOT EXISTS managed (symbol TEXT PRIMARY KEY, "
                        "status TEXT, entry_id TEXT, sl_id TEXT, tp_id TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS daily (day TEXT PRIMARY KEY, "
                        "opening_wallet TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS daily_halts ("
                        "day TEXT PRIMARY KEY, reason TEXT NOT NULL)")

    def mark_seen(self, symbol: str, candle_ms: int) -> bool:
        cursor = self.db.execute("INSERT OR IGNORE INTO seen VALUES (?, ?)",
                                 (symbol, candle_ms))
        return cursor.rowcount == 1

    def managed(self, symbol: str):
        row = self.db.execute("SELECT status,entry_id,sl_id,tp_id FROM managed "
                              "WHERE symbol=?", (symbol,)).fetchone()
        return dict(zip(("status", "entry_id", "sl_id", "tp_id"), row)) if row else None

    def set_managed(self, symbol, status, entry_id, sl_id=None, tp_id=None):
        self.db.execute("INSERT OR REPLACE INTO managed VALUES (?, ?, ?, ?, ?)",
                        (symbol, status, entry_id, sl_id, tp_id))

    def clear_managed(self, symbol):
        self.db.execute("DELETE FROM managed WHERE symbol=?", (symbol,))

    def check_daily_limit(self, wallet: Decimal, equity: Decimal):
        day = datetime.now(timezone.utc).date().isoformat()
        self.db.execute("INSERT OR IGNORE INTO daily VALUES (?, ?)", (day, str(wallet)))
        opening = decimal(self.db.execute(
            "SELECT opening_wallet FROM daily WHERE day=?", (day,)
        ).fetchone()[0])
        if self.db.execute("SELECT 1 FROM daily_halts WHERE day=?", (day,)).fetchone():
            raise SafetyError("Daily 5% loss circuit breaker latched until next UTC day")
        if min(wallet, equity) <= opening * (1 - MAX_DAILY_WALLET_DRAWDOWN):
            self.db.execute("INSERT OR IGNORE INTO daily_halts VALUES (?, ?)",
                            (day, "5% wallet/equity drawdown"))
            LOG.critical("Daily 5%% loss cap breached; persisted halt day=%s", day)
            raise SafetyError("Daily 5% wallet/equity drawdown circuit breaker active")


def exchange_client():
    if ccxt is None:
        raise SafetyError("CCXT is required: pip install ccxt")
    if LIVE:
        if os.getenv("SIGNALPILOT_LIVE_CONFIRM") != "I_ACCEPT_3X_LIVE_RISK":
            raise SafetyError("Live trading requires explicit arming")
        if not os.getenv("BINANCE_API_KEY") or not os.getenv("BINANCE_API_SECRET"):
            raise SafetyError("Missing Binance credentials")
    ex = ccxt.binanceusdm({
        "apiKey": os.getenv("BINANCE_API_KEY", "") if LIVE else "",
        "secret": os.getenv("BINANCE_API_SECRET", "") if LIVE else "",
        "enableRateLimit": True,
        "timeout": 15000,
        "options": {"adjustForTimeDifference": True},
    })
    ex.load_markets()
    for symbol in SYMBOLS:
        market = ex.market(symbol)
        if not market.get("linear") or market.get("active") is False:
            raise SafetyError(f"Invalid or inactive USD-M market: {symbol}")
    return ex


def raw_symbol(symbol: str) -> str:
    return SYMBOLS[symbol]


def ensure_one_way(ex):
    response = ex.fapiPrivateGetPositionSideDual()
    if str(response.get("dualSidePosition")).lower() != "false":
        raise SafetyError("Hedge Mode detected; bot requires One-way Mode")


def configure_symbol(ex, symbol: str):
    market_id = raw_symbol(symbol)
    try:
        ex.fapiPrivatePostMarginType({"symbol": market_id, "marginType": "ISOLATED"})
        LOG.info("Isolated margin set for %s", market_id)
    except Exception as exc:
        if ccxt is None or not isinstance(exc, ccxt.ExchangeError) or "-4046" not in str(exc):
            raise
        LOG.info("%s already has Isolated Margin", market_id)
    result = ex.fapiPrivatePostLeverage({"symbol": market_id, "leverage": LEVERAGE})
    if int(result.get("leverage", 0)) != LEVERAGE:
        raise SafetyError(f"Leverage confirmation failed: {market_id}")
    LOG.info("%s leverage confirmed at %sx", market_id, LEVERAGE)


def wallet_balance(ex) -> tuple[Decimal, Decimal, Decimal]:
    response = ex.fetch_balance({"type": "future"})
    info = response.get("info", [])
    assets = info.get("assets", []) if isinstance(info, dict) else info
    usdt = next((a for a in assets if a.get("asset") == "USDT"), None)
    if usdt is None:
        raise SafetyError("Cannot verify USDT walletBalance from Binance")
    wallet = decimal(usdt["balance"] if "walletBalance" not in usdt else usdt["walletBalance"])
    free = decimal(usdt["availableBalance"])
    if "marginBalance" not in usdt:
        raise SafetyError("Cannot verify USDT marginBalance including unrealized PnL")
    equity = decimal(usdt["marginBalance"])
    if wallet <= 0 or free <= 0 or equity <= 0:
        raise SafetyError("Insufficient USDT wallet/equity/available balance")
    return wallet, free, equity


def all_positions(ex) -> dict[str, dict]:
    result = {}
    for p in ex.fetch_positions():
        info = p.get("info") or {}
        if "positionAmt" not in info:
            raise SafetyError("Cannot verify raw Binance positionAmt")
        amount = decimal(info["positionAmt"])
        if amount:
            result[info["symbol"]] = {
                "amount": amount, "entry": decimal(info["entryPrice"]),
                "position_side": info.get("positionSide", "BOTH"),
            }
    return result


def open_algos(ex, symbol: str) -> list[dict]:
    result = ex.fapiPrivateGetOpenAlgoOrders({"symbol": raw_symbol(symbol)})
    if not isinstance(result, list):
        raise SafetyError("Cannot verify open Algo Orders")
    return result


def own_algos(ex, symbol: str) -> list[dict]:
    return [a for a in open_algos(ex, symbol)
            if str(a.get("clientAlgoId", "")).startswith(ALGO_PREFIX)
            and a.get("symbol", raw_symbol(symbol)) == raw_symbol(symbol)]


def cancel_owned_algos(ex, symbol: str):
    for order in own_algos(ex, symbol):
        ex.fapiPrivateDeleteAlgoOrder({"algoId": order["algoId"]})
        LOG.warning("Canceled remaining %s Algo Order %s", symbol, order["algoId"])
    if own_algos(ex, symbol):
        raise SafetyError(f"Could not clear all bot-owned Algo Orders for {symbol}")


def market_filters(ex, symbol: str) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    filters = {f["filterType"]: f for f in ex.market(symbol)["info"]["filters"]}
    lot = filters["LOT_SIZE"]
    market_lot = filters.get("MARKET_LOT_SIZE", lot)
    step = decimal(market_lot.get("stepSize", "0"))
    if step <= 0:
        step = decimal(lot["stepSize"])
    minimum = max(decimal(lot["minQty"]), decimal(market_lot.get("minQty", "0")))
    maximum = min(decimal(lot["maxQty"]), decimal(market_lot.get("maxQty", lot["maxQty"])))
    tick = decimal(filters["PRICE_FILTER"]["tickSize"])
    notional_filter = filters.get("MIN_NOTIONAL", filters.get("NOTIONAL"))
    if not notional_filter:
        raise SafetyError("Binance minimum notional filter unavailable")
    min_notional = decimal(notional_filter.get("notional", notional_filter.get("minNotional")))
    if step <= 0 or tick <= 0:
        raise SafetyError("Invalid exchange quantity/price filters")
    return step, minimum, maximum, tick, min_notional


def mark_price(ex, symbol: str) -> Decimal:
    result = ex.fapiPublicGetPremiumIndex({"symbol": raw_symbol(symbol)})
    mark = decimal(result["markPrice"])
    if mark <= 0:
        raise SafetyError("Invalid mark price")
    if result.get("time") is None:
        raise SafetyError("Missing Binance mark price timestamp")
    server_ms = ex.fetch_time()
    if server_ms is None or abs(int(server_ms) - int(result["time"])) > 10000:
        raise SafetyError("Stale Binance mark price")
    return mark


def signal_from_closed_bars(reference: list, signal_bar: list,
                            mark: Decimal):
    """Pure indicator calculation shared by live scanner and offline backtests.

    The 20 reference bars must be closed BEFORE the signal bar. The signal
    bar itself supplies volume only; its close is never in the VWAP window.
    """
    if len(reference) != WINDOW:
        raise SafetyError("Expected exactly 20 prior closed reference candles")
    volumes = [decimal(b[5]) for b in reference]
    prices = [(decimal(b[2]) + decimal(b[3]) + decimal(b[4])) / 3
              for b in reference]
    total_volume = sum(volumes)
    if total_volume <= 0:
        return None, D(0), D(0), decimal(signal_bar[5]), D(0)
    vwap = sum(p * v for p, v in zip(prices, volumes)) / total_volume
    variance = sum(v * (p - vwap) ** 2 for p, v in zip(prices, volumes)) / total_volume
    sigma = variance.sqrt()
    avg_volume = total_volume / WINDOW
    current_volume = decimal(signal_bar[5])
    side = None
    if sigma > 0 and current_volume >= VOLUME_MULTIPLIER * avg_volume:
        if mark <= vwap - 2 * sigma:
            side = "LONG"
        elif mark >= vwap + 2 * sigma:
            side = "SHORT"
    return side, vwap, sigma, current_volume, avg_volume


def calculate_signal(ex, symbol: str, now_ms: int):
    candles = ex.fetch_ohlcv(symbol, "15m", limit=25)
    closed = [bar for bar in candles if bar[0] + INTERVAL_MS <= now_ms - 1500]
    if len(closed) < WINDOW + 1:
        return None
    recent = closed[-WINDOW - 1:]
    if any(right[0] - left[0] != INTERVAL_MS
           for left, right in zip(recent, recent[1:])):
        raise SafetyError(f"Missing/duplicate/out-of-order 15m candle for {symbol}")
    for bar in recent:
        opening, high, low, close, volume = map(
            decimal, (bar[1], bar[2], bar[3], bar[4], bar[5])
        )
        if not (0 < low <= min(opening, close)
                and max(opening, close) <= high and volume >= 0):
            raise SafetyError(f"Invalid OHLCV data for {symbol}")
    signal_bar = closed[-1]
    candle_close = signal_bar[0] + INTERVAL_MS
    if not 0 <= now_ms - candle_close <= 12000:
        return None  # never trade stale or still-open candles
    reference = closed[-WINDOW - 1:-1]  # previous 20 CLOSED bars; no look-ahead
    mark = mark_price(ex, symbol)
    side, vwap, sigma, current_volume, avg_volume = signal_from_closed_bars(
        reference, signal_bar, mark,
    )
    LOG.info("%s candle=%s mark=%s vwap=%s sigma=%s volume=%s mean_volume=%s signal=%s",
             raw_symbol(symbol), signal_bar[0], mark, vwap, sigma,
             current_volume, avg_volume, side)
    return signal_bar[0], side, mark


def entry_quantity(ex, symbol: str, wallet: Decimal, free: Decimal,
                   mark: Decimal) -> Decimal:
    step, min_qty, max_qty, _, min_notional = market_filters(ex, symbol)
    margin = wallet * MARGIN_FRACTION
    notional_cap = margin * LEVERAGE
    if free < margin * D("1.02"):
        raise SafetyError("Not enough free margin for order and fee buffer")
    # A conservative entry-price buffer reduces avoidable post-fill 5% cap
    # breaches caused by market-order slippage. Final fill is rechecked.
    qty = floor_step(notional_cap / (mark * D("1.005")), step)
    if qty < min_qty or qty > max_qty or qty * mark < min_notional:
        raise SafetyError("Order below Binance minimum or above maximum after rounding")
    if qty * mark > notional_cap:
        raise SafetyError("5% margin allocation violated")
    return qty


def protection_prices(entry: Decimal, side: str, tick: Decimal):
    if side == "LONG":
        stop = round_tick(entry * (1 - STOP_FRACTION), tick, ROUND_UP)
        take = round_tick(entry * (1 + TAKE_FRACTION), tick, ROUND_UP)
        if not 0 < stop < entry < take:
            raise SafetyError("Invalid LONG stop/take rounding")
    else:
        stop = round_tick(entry * (1 + STOP_FRACTION), tick, ROUND_DOWN)
        take = round_tick(entry * (1 - TAKE_FRACTION), tick, ROUND_DOWN)
        if not 0 < take < entry < stop:
            raise SafetyError("Invalid SHORT stop/take rounding")
    risk_distance = abs(entry - stop)
    reward_distance = abs(take - entry)
    if reward_distance < 2 * risk_distance:
        raise SafetyError("Rounded protection violates 1:2 risk/reward")
    return stop, take


def algo_order(ex, symbol: str, side: str, kind: str, trigger: Decimal,
               client_id: str):
    return ex.fapiPrivatePostAlgoOrder({
        "algoType": "CONDITIONAL", "symbol": raw_symbol(symbol),
        "side": "SELL" if side == "LONG" else "BUY", "type": kind,
        "positionSide": "BOTH", "workingType": "MARK_PRICE",
        "triggerPrice": str(trigger), "closePosition": "true",
        "clientAlgoId": client_id,
        # No quantity and no reduceOnly with closePosition=true.
    })


def emergency_flatten(ex, symbol: str):
    for attempt in range(2):
        position = all_positions(ex).get(raw_symbol(symbol))
        if not position:
            return
        amount = position["amount"]
        ex.create_order(symbol, "market", "sell" if amount > 0 else "buy",
                        float(abs(amount)), None,
                        {"reduceOnly": True, "positionSide": "BOTH"})
        LOG.critical("Emergency reduce-only flatten attempt=%s symbol=%s", attempt + 1, symbol)
        time.sleep(1)
    if all_positions(ex).get(raw_symbol(symbol)):
        raise SafetyError(f"CRITICAL: residual unprotected position in {symbol}")


def reconcile(ex, state: State, positions: dict):
    for symbol in SYMBOLS:
        pos = positions.get(raw_symbol(symbol))
        managed = state.managed(symbol)
        if not pos:
            if managed and managed["status"] == "PENDING":
                # An ambiguous MARKET request can still fill after a timeout.
                # Never silently discard its pending marker or retry entry.
                raise SafetyError(f"Unresolved pending MARKET entry: {symbol}; inspect exchange")
            cancel_owned_algos(ex, symbol)  # closePosition does NOT cancel sibling
            if managed:
                LOG.info("Position closed: %s; sibling conditional orders removed", symbol)
                state.clear_managed(symbol)
            continue
        if not managed:
            LOG.warning("Existing external/unmanaged position %s; no new entry", symbol)
            continue
        if managed["status"] != "PROTECTED":
            LOG.critical("Pending entry after restart; flattening %s", symbol)
            emergency_flatten(ex, symbol)
            cancel_owned_algos(ex, symbol)
            # Keep PENDING after flatten. A timed-out MARKET can fill later.
            raise SafetyError(f"Unresolved pending MARKET entry: {symbol}; "
                              "emergency flatten attempted; manual reconciliation required")
        all_algos = open_algos(ex, symbol)
        actual_algos = [a for a in all_algos
                        if str(a.get("clientAlgoId", "")).startswith(ALGO_PREFIX)]
        actual_ids = {str(a["algoId"]) for a in actual_algos}
        expected_ids = {managed["sl_id"], managed["tp_id"]}
        expected_side = "SELL" if pos["amount"] > 0 else "BUY"
        direction = "LONG" if pos["amount"] > 0 else "SHORT"
        _, _, _, tick, _ = market_filters(ex, symbol)
        expected_stop, expected_take = protection_prices(pos["entry"], direction, tick)

        def matches_expected_algo(a):
            try:
                order_id = str(a["algoId"])
                is_stop = order_id == managed["sl_id"]
                expected_kind = "STOP_MARKET" if is_stop else "TAKE_PROFIT_MARKET"
                expected_trigger = expected_stop if is_stop else expected_take
                return (
                    str(a.get("type", a.get("orderType", ""))) == expected_kind
                    and str(a.get("closePosition", "")).lower() == "true"
                    and a.get("workingType") == "MARK_PRICE"
                    and a.get("positionSide", "BOTH") == "BOTH"
                    and a.get("side") == expected_side
                    and decimal(a.get("triggerPrice", "0")) == expected_trigger
                )
            except (ValueError, ArithmeticError, TypeError, KeyError, SafetyError):
                LOG.exception("Malformed Binance Algo protection: %s", symbol)
                return False

        invalid_protection = (
            len(all_algos) != len(actual_algos)
            or any(not matches_expected_algo(a) for a in actual_algos)
        )
        if actual_ids != expected_ids or invalid_protection:
            LOG.critical("Missing/extra protective Algo Order for %s: %s vs %s",
                         symbol, actual_ids, expected_ids)
            emergency_flatten(ex, symbol)
            cancel_owned_algos(ex, symbol)
            state.clear_managed(symbol)
            raise SafetyError(f"Protective orders failed reconciliation: {symbol}")


def execute_signal(ex, state: State, symbol: str, side: str,
                   candle_ms: int, observed_mark: Decimal):
    if not LIVE:
        LOG.warning("DRY_RUN signal: %s %s candle=%s mark=%s (NO ORDER)",
                    symbol, side, candle_ms, observed_mark)
        return
    ensure_one_way(ex)
    positions = all_positions(ex)
    if any(s not in SYMBOLS.values() for s in positions):
        raise SafetyError("Unmanaged external symbol positions exist; refusing entry")
    if any(state.managed(symbol) is None or
           state.managed(symbol)["status"] != "PROTECTED"
           for symbol in SYMBOLS if raw_symbol(symbol) in positions):
        raise SafetyError("Unmanaged or unprotected existing position; refusing entry")
    if len(positions) >= 2 or raw_symbol(symbol) in positions:
        return
    if state.managed(symbol) or open_algos(ex, symbol):
        raise SafetyError("Existing managed state or conditional orders: no new entry")
    configure_symbol(ex, symbol)  # only after verifying no position on target
    wallet, free, equity = wallet_balance(ex)
    state.check_daily_limit(wallet, equity)
    fresh_mark = mark_price(ex, symbol)
    if abs(fresh_mark / observed_mark - 1) > D("0.002"):
        raise SafetyError("Mark price moved >0.2% after signal; skip")
    qty = entry_quantity(ex, symbol, wallet, free, fresh_mark)
    entry_id = f"QMR_{raw_symbol(symbol)}_{candle_ms // 1000}_EN"
    state.set_managed(symbol, "PENDING", entry_id)  # durable before MARKET
    try:
        order = ex.create_order(symbol, "market", "buy" if side == "LONG" else "sell",
                                float(qty), None,
                                {"newClientOrderId": entry_id, "positionSide": "BOTH"})
        LOG.info("Entry ACK %s: %s", symbol, order.get("id"))
        time.sleep(0.6)
        position = all_positions(ex).get(raw_symbol(symbol))
        if not position:
            raise SafetyError("Entry acknowledged but no position found")
        if position["position_side"] != "BOTH":
            raise SafetyError("Unexpected hedge-mode position")
        entry = position["entry"]
        actual_margin = abs(position["amount"]) * entry / LEVERAGE
        if actual_margin > wallet * MARGIN_FRACTION:
            raise SafetyError("Post-fill margin exceeded 5% of pre-entry wallet")
        _, _, _, tick, _ = market_filters(ex, symbol)
        stop, take = protection_prices(entry, side, tick)
        current_mark = mark_price(ex, symbol)
        if (side == "LONG" and (current_mark <= stop or current_mark >= take)) or (
                side == "SHORT" and (current_mark >= stop or current_mark <= take)):
            raise SafetyError("Market crossed a protective trigger before bracket placement")
        base = f"QMR_{raw_symbol(symbol)}_{candle_ms // 1000}"
        # STOP first; Algo Service is not native OCO/OTO.
        sl = algo_order(ex, symbol, side, "STOP_MARKET", stop, base + "_SL")
        tp = algo_order(ex, symbol, side, "TAKE_PROFIT_MARKET", take, base + "_TP")
        sl_id, tp_id = str(sl["algoId"]), str(tp["algoId"])
        state.set_managed(symbol, "PROTECTED", entry_id, sl_id, tp_id)
        LOG.info("PROTECTED %s %s qty=%s entry=%s stop=%s take=%s sl=%s tp=%s",
                 symbol, side, qty, entry, stop, take, sl_id, tp_id)
        reconcile(ex, state, all_positions(ex))
    except Exception:
        LOG.exception("Entry/bracket failed: emergency flatten and cleanup %s", symbol)
        try:
            emergency_flatten(ex, symbol)
            cancel_owned_algos(ex, symbol)
            # Keep PENDING after an ambiguous entry failure, even if flat:
            # the exchange may acknowledge/fill a timed-out MARKET later.
            # A human must reconcile the entry ID before restarting.
            LOG.critical("HALTED %s: verify entry ID %s manually before resuming",
                         symbol, entry_id)
        except Exception:
            LOG.critical("CRITICAL: manual intervention required for %s", symbol,
                         exc_info=True)
        raise


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # One process only, so two workers cannot enter the same symbol concurrently.
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_file = open(str(DB_PATH) + ".lock", "a+")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise SafetyError("Another bot instance is already running") from exc
    state = State(DB_PATH)
    ex = exchange_client()
    if LIVE:
        ensure_one_way(ex)
        startup_positions = all_positions(ex)
        reconcile(ex, state, startup_positions)
        for symbol in SYMBOLS:
            if raw_symbol(symbol) not in startup_positions:
                configure_symbol(ex, symbol)
    LOG.warning("SignalPilot mode=%s leverage=%sx; symbols=%s",
                "LIVE" if LIVE else "DRY_RUN", LEVERAGE, list(SYMBOLS.values()))
    last_reconcile = 0.0
    try:
        while True:
            try:
                now_ms = ex.fetch_time()  # exchange clock, not workstation clock
                if now_ms is None:
                    raise SafetyError("Cannot verify Binance server time")
                if LIVE and time.monotonic() - last_reconcile >= 4:
                    reconcile(ex, state, all_positions(ex))
                    last_reconcile = time.monotonic()
                # Keep managing existing positions even with the entry kill switch.
                if Path("STOP_TRADING").exists():
                    time.sleep(2)
                    continue
                if not 1500 <= now_ms % INTERVAL_MS <= 14000:
                    time.sleep(2)
                    continue
                for symbol in SYMBOLS:
                    result = calculate_signal(ex, symbol, now_ms)
                    if result is None:
                        continue
                    candle_ms, side, mark = result
                    if not state.mark_seen(symbol, candle_ms):
                        continue
                    if side:
                        execute_signal(ex, state, symbol, side, candle_ms, mark)
                time.sleep(2)
            except (SafetyError, sqlite3.Error) + CCXT_ERRORS:
                LOG.exception("Exchange/safety/storage error; fail closed")
                if LIVE:
                    raise  # stop entries; native protective orders remain on exchange
                time.sleep(5)
    finally:
        ex.close()
        state.db.close()
        lock_file.close()


if __name__ == "__main__":
    main()