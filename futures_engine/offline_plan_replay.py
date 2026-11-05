"""Offline, order-free single-plan OHLCV replay. No exchange or network imports.

All candles must be closed, sorted and strictly contiguous at the selected interval.
Results are *hypothetical*, never evidence of exchange fills.
"""
from decimal import Decimal, InvalidOperation

def D(value):
    try:
        v = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise ValueError("invalid_number") from exc
    if not v.is_finite():
        raise ValueError("nonfinite_number")
    return v

def replay(plan, candles, *, interval_ms=300000, fee_rate="0.0005",
           slippage_rate="0.0002", initial_equity="150",
           max_holding_minutes=None, max_candles=48):
    """Candles: (open_time_ms, open, high, low, close), all CLOSED.

    Entry is a hypothetical market fill at the NEXT candle open after signal close,
    not at the signal close. Stop-first if both exit brackets hit the same bar.
    No funding assumption: funding is not included in this P&L.
    Optional maximum holding time closes at the completed candle close,
    unless stop/target triggers first. No artificial exit on missing bars.
    Evaluation beyond max_candles (default 48) is excluded, and an
    unresolved 48-bar evaluation returns UNKNOWN, never realized profit.
    """
    if not isinstance(plan, dict) or plan.get("status") != "INDICATIVE_PLAN_ONLY_NOT_EXECUTABLE":
        raise ValueError("unvalidated_plan")
    if any(plan.get(k) is not False for k in
           ("orders_sent", "execution_authorized", "risk_snapshot_approved")):
        raise ValueError("execution_not_disabled")
    side = plan.get("side")
    if side not in ("long", "short"):
        raise ValueError("invalid_side")
    entry, stop, target, qty = [D(plan[k]) for k in ("entry", "stop", "target", "quantity")]
    fee, slip, equity = D(fee_rate), D(slippage_rate), D(initial_equity)
    if any(x <= 0 for x in (entry, stop, target, qty, equity)) or fee < 0 or slip < 0:
        raise ValueError("invalid_parameters")
    if not ((stop < entry < target) if side == "long" else (target < entry < stop)):
        raise ValueError("invalid_brackets")
    if not isinstance(interval_ms, int) or interval_ms <= 0:
        raise ValueError("invalid_interval")
    if type(max_candles) is not int or max_candles <= 0:
        raise ValueError("invalid_horizon")
    if max_holding_minutes is not None:
        if (type(max_holding_minutes) is not int or
            max_holding_minutes <= 0 or
            (max_holding_minutes * 60000) % interval_ms):
            raise ValueError("invalid_max_holding_minutes")
    signal_close = plan.get("closed_5m_candle_ms")
    if type(signal_close) is not int or signal_close % interval_ms:
        raise ValueError("invalid_signal_candle")
    if not candles:
        return {"status": "UNKNOWN", "reason": "missing_closed_candles", "orders_sent": False}
    parsed = []
    previous = None
    for raw in candles:
        if len(raw) != 5 or type(raw[0]) is not int:
            raise ValueError("invalid_candle")
        t = raw[0]
        o,h,l,c = map(D, raw[1:])
        if min(o,h,l,c) <= 0 or h < max(o,c,l) or l > min(o,c,h):
            raise ValueError("invalid_ohlc")
        if previous is not None and t != previous + interval_ms:
            return {"status": "UNKNOWN", "reason": "missing_or_duplicate_candles", "orders_sent": False}
        parsed.append((t,o,h,l,c))
        previous = t
    # A candle timestamp denotes its OPEN. The first eligible candle opens at
    # signal_close (the end of the signal candle).
    if parsed[0][0] != signal_close:
        return {"status": "UNKNOWN", "reason": "missing_entry_candle", "orders_sent": False}
    first = parsed[0][1]
    # Market-open fill assumption with adverse slippage.
    fill = first * (1 + slip if side == "long" else 1 - slip)
    # Do not treat a wildly gapped market as a valid risk-approved entry.
    if (side == "long" and fill <= stop) or (side == "short" and fill >= stop):
        return {"status": "REJECTED", "reason": "gap_through_stop", "orders_sent": False}
    planned_risk = qty * abs(fill - stop) + fee * qty * (fill + stop) + slip * qty * stop
    if qty * fill > equity * 2 or planned_risk > D("1.50"):
        return {"status": "REJECTED", "reason": "risk_or_leverage_cap", "orders_sent": False}
    for t,o,h,l,c in parsed[:max_candles]:
        # Conservative exit when stop and target both occur within one bar.
        stop_hit = l <= stop if side == "long" else h >= stop
        target_hit = h >= target if side == "long" else l <= target
        if stop_hit or target_hit:
            reason = "STOP" if stop_hit else "TARGET"
            level = stop if stop_hit else target
            # Adverse gap open through stop, never assume stop-level execution.
            if stop_hit:
                level = min(level,o) if side == "long" else max(level,o)
            exit_fill = level * (1 - slip if side == "long" else 1 + slip)
            gross = qty * (exit_fill - fill) * (1 if side == "long" else -1)
            fees = qty * (fill + exit_fill) * fee
            return {"status": "CLOSED_HYPOTHETICAL", "exit_reason": reason,
                    "exit_candle_ms": t, "entry_fill": str(fill),
                    "exit_fill": str(exit_fill), "gross_pnl": str(gross),
                    "fees": str(fees), "net_pnl_excluding_funding": str(gross-fees),
                    "orders_sent": False}
        # A time limit expires only AFTER this entire closed candle has elapsed.
        # Stop/target checks above always take priority, even at the cap.
        if (max_holding_minutes is not None and
            t + interval_ms - signal_close >= max_holding_minutes * 60000):
            exit_fill = c * (1 - slip if side == "long" else 1 + slip)
            gross = qty * (exit_fill - fill) * (1 if side == "long" else -1)
            fees = qty * (fill + exit_fill) * fee
            return {"status": "CLOSED_HYPOTHETICAL", "exit_reason": "TIME_LIMIT",
                    "exit_candle_ms": t, "entry_fill": str(fill),
                    "exit_fill": str(exit_fill), "gross_pnl": str(gross),
                    "fees": str(fees), "net_pnl_excluding_funding": str(gross-fees),
                    "orders_sent": False}
    if len(parsed) >= max_candles:
        return {"status": "UNKNOWN", "reason": "evaluation_horizon_elapsed",
                "last_evaluated_candle_ms": parsed[max_candles - 1][0],
                "orders_sent": False}
    return {"status": "OPEN_HYPOTHETICAL", "entry_fill": str(fill),
            "last_closed_candle_ms": parsed[-1][0],
            "orders_sent": False, "unrealized_pnl_not_reported": True}
