"""Offline four-symbol risk and margin replay for hypothetical research plans.

This module does not import exchange clients, send orders, modify account data,
or operate on persistent Paper ledgers. Every record is evaluated independently
per requested holding horizon, using a single chronological portfolio ledger.
Results are retrospective scenarios, NOT proofs of realizable fills or profit.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from .offline_resized_horizon_study import study_resized_horizons

SYMBOLS = ("BTC", "ETH", "SOL", "XRP")
STEP_MS = 300000
DAILY_BARS = 288


def _number(value):
    if isinstance(value, bool):
        raise ValueError("invalid_portfolio_number")
    try:
        result = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise ValueError("invalid_portfolio_number") from exc
    if not result.is_finite():
        raise ValueError("invalid_portfolio_number")
    return result


def _utc_day(time_ms):
    return datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc).date()


def simulate_one_day(records, *, horizon_minutes, as_of_ms, market_limits,
                     initial_equity_per_coin="37.50", fee_rate="0.0006",
                     slippage_rate="0.0005"):
    """Run a single-UTC-day, four-coin, non-executable portfolio scenario.

    Records: {signal_id, symbol, signal_candle_open_ms, plan, candles}.
    market_limits: explicit offline {BTC,...} -> amount_step/min_amount/min_notional.
    Exit releases risk/margin only when that entire exit candle is closed.
    Current positions block overlapping signals for the same symbol.
    Returns UNKNOWN for a missing future outcome; never books that PnL.
    Candidates whose horizon can cross UTC midnight are excluded: no invented
    intraday mark-to-market or reset for positions crossing the day boundary.
    """
    if type(horizon_minutes) is not int or horizon_minutes not in (15, 30, 60, 90):
        raise ValueError("unsupported_research_horizon")
    if type(as_of_ms) is not int or as_of_ms <= 0:
        raise ValueError("invalid_as_of_ms")
    if not isinstance(records, (list, tuple)) or not isinstance(market_limits, dict):
        raise ValueError("invalid_research_inputs")
    if set(market_limits) != set(SYMBOLS):
        raise ValueError("four_explicit_market_limits_required")
    initial = _number(initial_equity_per_coin)
    if initial <= 0 or initial > Decimal("37.50"):
        raise ValueError("initial_paper_allocation_exceeds_ledger")
    fee = _number(fee_rate)
    slip = _number(slippage_rate)
    if fee < 0 or slip < 0:
        raise ValueError("invalid_execution_costs")

    cash = {symbol: initial for symbol in SYMBOLS}
    daily_start = dict(cash)
    starting_total = initial * len(SYMBOLS)
    active = {}
    seen = set()
    events = []
    max_reserved_risk = Decimal("0")
    max_reserved_margin = Decimal("0")
    closed = 0
    closed_pnl = Decimal("0")
    scenario_day = None

    def reserved():
        return sum((p["risk"] for p in active.values()), Decimal("0"))

    def margin_reserved():
        return sum((p["margin"] for p in active.values()), Decimal("0"))

    def record_max():
        nonlocal max_reserved_risk, max_reserved_margin
        max_reserved_risk = max(max_reserved_risk, reserved())
        max_reserved_margin = max(max_reserved_margin, margin_reserved())

    def release_due(at_ms):
        nonlocal closed, closed_pnl
        due = sorted(
            ((p["exit_at_ms"], symbol) for symbol, p in active.items()
             if p["exit_at_ms"] is not None and p["exit_at_ms"] <= at_ms)
        )
        for completed_at, symbol in due:
            item = active.pop(symbol)
            profit = item["pnl"]
            cash[symbol] += profit
            closed += 1
            closed_pnl += profit
            events.append({"event": "CLOSED_HYPOTHETICAL",
                           "signal_id": item["signal_id"],
                           "symbol": symbol, "at_ms": completed_at,
                           "exit_reason": item["exit_reason"],
                           "net_pnl_excluding_funding_usdt": str(profit),
                           "orders_sent": False})

    def note(signal_id, symbol, entry_at, status, reason):
        events.append({"event": status, "signal_id": signal_id,
                       "symbol": symbol, "at_ms": entry_at,
                       "reason": reason, "orders_sent": False})

    normalized = []
    for item in records:
        if not isinstance(item, dict):
            raise ValueError("invalid_signal_record")
        symbol = item.get("symbol")
        sid = item.get("signal_id")
        timestamp = item.get("signal_candle_open_ms")
        if symbol not in SYMBOLS or not isinstance(sid, str) or not sid:
            raise ValueError("invalid_signal_identity")
        if (type(timestamp) is not int or timestamp < 0 or
                timestamp % STEP_MS):
            raise ValueError("invalid_signal_time")
        if sid in seen:
            raise ValueError("duplicate_signal_id")
        seen.add(sid)
        plan = item.get("plan")
        if (not isinstance(plan, dict) or
                plan.get("closed_5m_candle_ms") != timestamp or
                plan.get("status") != "INDICATIVE_PLAN_ONLY_NOT_EXECUTABLE"):
            raise ValueError("invalid_archived_research_plan")
        candles = item.get("candles")
        if not isinstance(candles, (list, tuple)):
            raise ValueError("invalid_research_candles")
        entry_at = timestamp + STEP_MS
        if entry_at > as_of_ms:
            raise ValueError("future_signal_not_yet_known")
        day = _utc_day(entry_at)
        if scenario_day is None:
            scenario_day = day
        elif scenario_day != day:
            raise ValueError("multi_day_portfolio_requires_separate_daily_runs")
        normalized.append((entry_at, symbol, sid, timestamp, plan, candles))

    # An independent research plan must not invent a different market history
    # for a timestamp already present in another plan for the same symbol.
    # Validate ALL candidate histories before replay, even if a later signal
    # would ultimately be skipped due to an open position.
    history_by_symbol_and_open = {}
    for _entry_at, symbol, _sid, _signal_open, _plan, candle_history in normalized:
        for candle in candle_history:
            if (not isinstance(candle, (list, tuple)) or
                    len(candle) != 5 or
                    type(candle[0]) is not int or
                    candle[0] < 0 or candle[0] % STEP_MS):
                raise ValueError("invalid_portfolio_candle")
            try:
                prices = tuple(_number(price) for price in candle[1:])
            except ValueError as exc:
                raise ValueError("invalid_portfolio_candle") from exc
            opening, high, low, closing = prices
            if (min(prices) <= 0 or
                    high < max(opening, closing, low) or
                    low > min(opening, closing, high)):
                raise ValueError("invalid_portfolio_candle")
            key = (symbol, candle[0])
            previous = history_by_symbol_and_open.get(key)
            if previous is not None and previous != prices:
                raise ValueError("conflicting_symbol_candle_history")
            history_by_symbol_and_open[key] = prices

    normalized.sort(key=lambda item: (item[0], item[1], item[2]))
    for entry_at, symbol, sid, timestamp, plan, candles in normalized:
        # Only previously CLOSED exits can free resources at this entry time.
        release_due(entry_at)
        if symbol in active:
            note(sid, symbol, entry_at, "SKIPPED_RESEARCH_ONLY",
                 "overlapping_same_symbol_position")
            continue
        last_possible_close = entry_at + horizon_minutes * 60000
        if _utc_day(last_possible_close - 1) != scenario_day:
            note(sid, symbol, entry_at, "SKIPPED_RESEARCH_ONLY",
                 "horizon_crosses_utc_day")
            continue

        limit = market_limits[symbol]
        if not isinstance(limit, dict) or any(
                field not in limit for field in (
                    "amount_step", "min_amount", "min_notional")):
            raise ValueError("missing_symbol_market_limit")
        available = cash[symbol]  # never pool margin from other coins
        portfolio_equity = sum(cash.values(), Decimal("0"))
        if portfolio_equity > starting_total * Decimal("2"):
            # This study deliberately does not assume unverified profit-based
            # capital increases can unlock larger trade size.
            note(sid, symbol, entry_at, "SKIPPED_RESEARCH_ONLY",
                 "unverified_portfolio_growth")
            continue
        result = study_resized_horizons(
            plan, candles, signal_candle_open_ms=timestamp,
            as_of_ms=as_of_ms, horizons=(horizon_minutes,),
            amount_step=limit["amount_step"],
            min_amount=limit["min_amount"],
            min_notional=limit["min_notional"],
            paper_equity=str(available),
            day_start_equity=str(daily_start[symbol]),
            available_margin=str(available),
            portfolio_equity=str(portfolio_equity),
            portfolio_day_start_equity=str(starting_total),
            portfolio_open_risk=str(reserved()),
            fee_rate=str(fee), slippage_rate=str(slip),
        )
        if result["status"] != "OFFLINE_RESIZED_HORIZON_STUDY":
            note(sid, symbol, entry_at, result["status"],
                 result.get("reason", "research_incomplete"))
            continue
        selected = result["results"][str(horizon_minutes)]
        if selected["status"] not in (
                "CLOSED_HYPOTHETICAL", "OPEN_HYPOTHETICAL", "UNKNOWN",
                "REJECTED"):
            raise ValueError("unexpected_replay_status")
        if selected["status"] == "REJECTED":
            note(sid, symbol, entry_at, "REJECTED_RESEARCH_ONLY",
                 selected.get("reason", "replay_rejected"))
            continue

        risk = _number(result["sizing"]["estimated_stop_risk_usdt"])
        margin = _number(result["sizing"]["estimated_margin_usdt"])
        total_budget = min(Decimal("1.50"),
                           portfolio_equity * Decimal("0.01"))
        if (risk <= 0 or margin <= 0 or
                reserved() + risk > total_budget or
                margin_reserved() + margin > portfolio_equity or
                risk > available * Decimal("0.01") or
                margin > available):
            note(sid, symbol, entry_at, "REJECTED_RESEARCH_ONLY",
                 "concurrent_portfolio_risk_or_margin")
            continue

        if selected["status"] == "CLOSED_HYPOTHETICAL":
            end_ms = selected["exit_candle_ms"] + STEP_MS
            if end_ms <= entry_at or end_ms > as_of_ms:
                raise ValueError("invalid_hypothetical_exit_time")
            profit = _number(selected["net_pnl_excluding_funding"])
            exit_reason = selected["exit_reason"]
        else:
            # Unknown/open is a still-reserved position: no invented profit
            # and no premature collateral release.
            end_ms = None
            profit = Decimal("0")
            exit_reason = selected["status"]
        active[symbol] = {
            "signal_id": sid, "risk": risk, "margin": margin,
            "exit_at_ms": end_ms, "pnl": profit, "exit_reason": exit_reason,
        }
        record_max()
        events.append({"event": "ACCEPTED_RESEARCH_ONLY",
                       "signal_id": sid, "symbol": symbol, "at_ms": entry_at,
                       "reserved_risk_usdt": str(risk),
                       "reserved_margin_usdt": str(margin),
                       "modeled_exit": exit_reason,
                       "orders_sent": False})

    release_due(as_of_ms)
    return {
        "status": "OFFLINE_FOUR_COIN_PORTFOLIO_STUDY",
        "orders_sent": False, "execution_authorized": False,
        "funding_included": False, "actual_fills_verified": False,
        "horizon_minutes": horizon_minutes,
        "initial_total_usdt": str(starting_total),
        "final_closed_balance_usdt": str(sum(cash.values(), Decimal("0"))),
        "final_balance_by_symbol_usdt":
            {symbol: str(cash[symbol]) for symbol in SYMBOLS},
        "closed_hypothetical_count": closed,
        "closed_net_pnl_excluding_funding_usdt": str(closed_pnl),
        "max_concurrent_reserved_risk_usdt": str(max_reserved_risk),
        "max_concurrent_reserved_margin_usdt": str(max_reserved_margin),
        "end_reserved_risk_usdt": str(reserved()),
        "end_reserved_margin_usdt": str(margin_reserved()),
        "unresolved_positions": sorted(active),
        "events": events,
        "limitations": ("Single UTC day, four separate per-coin ledgers; "
                        "no live fills, funding, latency or authenticated "
                        "historical exchange-limit provenance."),
    }


def compare_four_coin_horizons(records, *, as_of_ms, market_limits,
                                horizons=(15, 30, 60, 90),
                                initial_equity_per_coin="37.50",
                                fee_rate="0.0006",
                                slippage_rate="0.0005"):
    """Each horizon starts from the same untouched research records/equity."""
    if not isinstance(horizons, (tuple, list)) or not horizons:
        raise ValueError("invalid_horizons")
    if len(set(horizons)) != len(horizons):
        raise ValueError("duplicate_horizons")
    outputs = {}
    for horizon in horizons:
        if type(horizon) is not int:
            raise ValueError("unsupported_research_horizon")
        outputs[str(horizon)] = simulate_one_day(
            records, horizon_minutes=horizon,
            as_of_ms=as_of_ms, market_limits=market_limits,
            initial_equity_per_coin=initial_equity_per_coin,
            fee_rate=fee_rate, slippage_rate=slippage_rate)
    return {"status": "OFFLINE_PORTFOLIO_HORIZON_COMPARISON",
            "orders_sent": False, "execution_authorized": False,
            "outcomes": outputs}
