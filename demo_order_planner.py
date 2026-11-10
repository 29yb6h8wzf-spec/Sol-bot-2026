"""Read-only, indicative Binance Futures DEMO order plan from closed candles.

This module cannot submit orders. Plans are NOT executable approvals:
exchange prices, margin, fees, account PnL and risk must be revalidated.
"""
from decimal import Decimal as D, ROUND_DOWN, ROUND_UP

MAX_MARGIN_FRACTION = D("0.05")

SYMBOLS = frozenset(("BTC/USDT:USDT", "ETH/USDT:USDT",
                     "SOL/USDT:USDT", "XRP/USDT:USDT"))


def dec(value):
    v = D(str(value))
    if not v.is_finite():
        raise ValueError("nonfinite_number")
    return v


def rounded(value, increment, mode):
    return (value / increment).to_integral_value(rounding=mode) * increment


def plan(verified, bars, *, tick, step, min_qty, min_cost, now_ms,
         capital="150", leverage=2, max_risk="1.50"):
    if not isinstance(verified, dict) or verified.get("symbol") not in SYMBOLS:
        raise ValueError("invalid_verified_symbol")
    if verified.get("source") != "verified_85_score_engine":
        raise ValueError("unverified_source")
    if type(verified.get("score")) is not int or not 85 <= verified["score"] <= 100:
        raise ValueError("score_below_85")
    proof = verified.get("verification")
    if (not isinstance(proof, dict) or
            proof.get("status") != "RECALCULATED_RESEARCH_CANDIDATE" or
            proof.get("score_verified_independently") is not True or
            proof.get("execution_authorized") is not False):
        raise ValueError("independent_proof_required")
    side = verified.get("direction")
    if side not in ("long", "short"):
        raise ValueError("invalid_direction")
    if not isinstance(bars, list) or len(bars) < 16:
        raise ValueError("insufficient_candles")
    if type(now_ms) is not int or type(verified.get("closed_5m_candle_ms")) is not int:
        raise ValueError("invalid_candle_time")
    times = [int(b[0]) for b in bars]
    if any(b - a != 300000 for a, b in zip(times, times[1:])):
        raise ValueError("gapped_candles")
    if times[-1] != verified["closed_5m_candle_ms"]:
        raise ValueError("verified_candle_mismatch")
    if not 0 <= now_ms - (times[-1] + 300000) <= 420000:
        raise ValueError("stale_candle")
    tick, step, min_qty, min_cost = map(dec, (tick, step, min_qty, min_cost))
    capital, max_risk = dec(capital), dec(max_risk)
    if min(tick, step, capital, max_risk) <= 0 or min_qty < 0 or min_cost < 0:
        raise ValueError("invalid_limits")
    if leverage != 2 or capital > 150 or max_risk > D("1.50"):
        raise ValueError("capital_or_leverage_exceeded")
    highs = [dec(b[2]) for b in bars]
    lows = [dec(b[3]) for b in bars]
    closes = [dec(b[4]) for b in bars]
    if any(not (0 < l <= c <= h) for h, l, c in zip(highs, lows, closes)):
        raise ValueError("invalid_bars")
    true_ranges = [
        max(highs[i] - lows[i], abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1]))
        for i in range(len(bars) - 14, len(bars))
    ]
    atr = sum(true_ranges) / D(14)
    entry = closes[-1]
    distance = max(atr * D("1.5"), entry * D("0.003"))
    if side == "long":
        stop = rounded(entry - distance, tick, ROUND_DOWN)
        target = rounded(entry + 2 * (entry - stop), tick, ROUND_UP)
    else:
        stop = rounded(entry + distance, tick, ROUND_UP)
        target = rounded(entry - 2 * (stop - entry), tick, ROUND_DOWN)
    if min(stop, target) <= 0:
        raise ValueError("invalid_brackets")
    risk_per_unit = abs(entry - stop)
    if risk_per_unit <= 0:
        raise ValueError("zero_stop_distance")
    quantity = rounded(min(max_risk / risk_per_unit,
                           capital * MAX_MARGIN_FRACTION * D(leverage) / entry), step, ROUND_DOWN)
    if quantity <= 0 or quantity < min_qty or quantity * entry < min_cost:
        raise ValueError("below_exchange_minimum")
    if quantity * risk_per_unit > max_risk or quantity * entry > capital * MAX_MARGIN_FRACTION * D(leverage):
        raise ValueError("risk_cap_exceeded")
    return {
        "symbol": verified["symbol"], "side": side,
        "source": "verified_85_score_engine", "score": verified["score"],
        "signal_id": verified["signal_id"],
        "closed_5m_candle_ms": times[-1],
        "entry": str(entry), "stop": str(stop), "target": str(target),
        "quantity": str(quantity), "estimated_max_stop_loss_before_fees":
            str(quantity * risk_per_unit),
        "estimated_notional": str(quantity * entry),
        "status": "INDICATIVE_PLAN_ONLY_NOT_EXECUTABLE",
        "orders_sent": False,
    }
