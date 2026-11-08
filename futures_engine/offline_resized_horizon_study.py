"""Pure offline sensitivity for risk-reduced, non-executable research plans.

No network, exchange clients, credentials, persistence, ledger mutations or
execution calls. This is NOT a live Paper engine or an order planner.
"""
from .offline_horizon_comparison import (
    HORIZONS_MINUTES,
    compare_research_open_time,
)
from .offline_risk_resizing import research_resize


def study_resized_horizons(
    plan, candles, *, signal_candle_open_ms, as_of_ms,
    amount_step, min_amount, min_notional,
    paper_equity, day_start_equity, available_margin,
    portfolio_equity, portfolio_day_start_equity, portfolio_open_risk,
    horizons=HORIZONS_MINUTES,
    fee_rate="0.0006", slippage_rate="0.0005",
):
    """Return conservative, independent hypothetical outcomes for each horizon.

    The account and exchange-limit inputs are REQUIRED: this helper must never
    silently treat four 37.50-USDT ledgers as a pooled 150-USDT allocation.
    It expects 5m OHLCV candle opens and requires evidence all bars are closed
    as of the caller's supplied historical observation time.
    """
    if (not isinstance(plan, dict) or
        plan.get("status") != "INDICATIVE_PLAN_ONLY_NOT_EXECUTABLE" or
        any(plan.get(k) is not False for k in (
            "orders_sent", "execution_authorized", "risk_snapshot_approved"))):
        raise ValueError("non_executable_plan_required")
    interval = 300000
    if (type(signal_candle_open_ms) is not int or
            signal_candle_open_ms < 0 or
            signal_candle_open_ms % interval or
            plan.get("closed_5m_candle_ms") != signal_candle_open_ms):
        raise ValueError("research_plan_timestamp_mismatch")
    if type(as_of_ms) is not int or as_of_ms < 0:
        raise ValueError("invalid_historical_as_of_ms")
    if not isinstance(candles, (tuple, list)):
        raise ValueError("invalid_candles")

    basic = {"orders_sent": False, "execution_authorized": False,
             "research_signal_candle_open_ms": signal_candle_open_ms,
             "first_possible_entry_candle_open_ms":
                 signal_candle_open_ms + interval}
    if not candles or as_of_ms < signal_candle_open_ms + interval * 2:
        return {**basic, "status": "UNKNOWN_RESEARCH_ONLY",
                "reason": "no_confirmed_entry_bar"}
    expected_first = signal_candle_open_ms + interval
    if (not isinstance(candles[0], (tuple, list)) or
            len(candles[0]) != 5 or
            type(candles[0][0]) is not int or
            candles[0][0] != expected_first):
        return {**basic, "status": "UNKNOWN_RESEARCH_ONLY",
                "reason": "missing_first_eligible_candle"}
    # Never use a future or currently forming candle as a completed OHLC bar.
    for candle in candles:
        if (not isinstance(candle, (tuple, list)) or len(candle) != 5 or
                type(candle[0]) is not int or
                candle[0] < expected_first or
                candle[0] + interval > as_of_ms):
            return {**basic, "status": "UNKNOWN_RESEARCH_ONLY",
                    "reason": "unclosed_or_invalid_future_candle"}

    sizing = research_resize(
        plan, next_candle_open=candles[0][1],
        amount_step=amount_step, min_amount=min_amount,
        min_notional=min_notional, paper_equity=paper_equity,
        day_start_equity=day_start_equity,
        available_margin=available_margin,
        portfolio_equity=portfolio_equity,
        portfolio_day_start_equity=portfolio_day_start_equity,
        portfolio_open_risk=portfolio_open_risk,
        fee_rate=fee_rate, slippage_rate=slippage_rate)
    if sizing["status"] != "RESIZED_RESEARCH_ONLY":
        return {**basic, "status": "REJECTED_RESEARCH_ONLY",
                "reason": sizing["reason"], "sizing": sizing}

    # Never alter the archived plan; only use its smaller *theoretical*
    # quantity for this isolated replay. Replay remains hard-blocked from
    # all executable, Demo, or Live plan statuses.
    research_plan = dict(plan)
    research_plan["quantity"] = sizing["research_quantity"]
    comparison = compare_research_open_time(
        research_plan, signal_candle_open_ms=signal_candle_open_ms,
        candles=candles, horizons=horizons,
        fee_rate=fee_rate, slippage_rate=slippage_rate,
        initial_equity=portfolio_equity)
    return {**basic, "status": "OFFLINE_RESIZED_HORIZON_STUDY",
            "sizing": sizing, "horizons_minutes": list(horizons),
            "results": comparison["results"],
            "funding_included": False,
            "actual_fills_verified": False}
