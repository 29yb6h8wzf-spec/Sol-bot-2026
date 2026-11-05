"""Read-only, four-coin portfolio replay of indicative research candidates.

Only archived, NON-EXECUTABLE plans with caller-supplied closed OHLC candles and
exchange limits are accepted. No exchange/network access, secrets, persistence,
order methods or production ledger mutations.

Each coin starts with its OWN 37.50-USDT Paper allocation; the portfolio starts
with 150 USDT. Sizing honors 1% per-coin equity, 5% UTC-day losses, 2x per-coin
free margin, and reserved portfolio risk. Equal-timestamp candidates are
processed by symbol name (deterministic, NOT an alpha/score ranking).
Results are hypothetical, with modeled fees/slippage but without funding,
latency, mark-to-market margin or actual Binance executions.
"""
from datetime import datetime, timezone
from decimal import Decimal

from .offline_horizon_comparison import HORIZONS_MINUTES
from .offline_resized_horizon_study import study_resized_horizons

STEP_MS = 300_000
COINS = ("BTC", "ETH", "SOL", "XRP")
INITIAL_EACH = Decimal("37.50")
INITIAL_TOTAL = INITIAL_EACH * len(COINS)


def _day(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date()


def _valid(candidates, horizons):
    if not isinstance(candidates, (list, tuple)):
        raise ValueError("invalid_candidates")
    if not isinstance(horizons, (list, tuple)) or not horizons:
        raise ValueError("invalid_horizons")
    if len(set(horizons)) != len(horizons):
        raise ValueError("duplicate_horizons")
    if any(type(h) is not int or h <= 0 or h % 5 or h > 240
           for h in horizons):
        raise ValueError("invalid_horizon_minutes")
    ordered = []
    seen = set()
    for record in candidates:
        if not isinstance(record, dict):
            raise ValueError("invalid_candidate")
        symbol = record.get("symbol")
        if symbol not in tuple(f"{c}/USDT:USDT" for c in COINS):
            raise ValueError("unsupported_symbol")
        t = record.get("signal_candle_open_ms")
        if type(t) is not int or t < 0 or t % STEP_MS:
            raise ValueError("invalid_signal_candle")
        plan = record.get("plan")
        if not isinstance(plan, dict) or (
            plan.get("symbol") not in (None, symbol)
        ):
            raise ValueError("plan_symbol_mismatch")
        key = (symbol, t)
        if key in seen:
            raise ValueError("duplicate_symbol_candle")
        seen.add(key)
        if (not isinstance(record.get("candles"), (list, tuple)) or
            type(record.get("as_of_ms")) is not int or
            not isinstance(record.get("exchange_limits"), dict)):
            raise ValueError("incomplete_historical_candidate")
        limits = record["exchange_limits"]
        if not all(k in limits for k in (
            "amount_step", "min_amount", "min_notional")):
            raise ValueError("missing_exchange_limits")
        ordered.append(record)
    return sorted(ordered, key=lambda r:
                  (r["signal_candle_open_ms"], r["symbol"]))


def simulate_portfolio(candidates, *, horizons=HORIZONS_MINUTES,
                       fee_rate="0.0006", slippage_rate="0.0005"):
    """Retrospective 4-coin study: independent portfolio path for each horizon.

    Entry decisions use only the candidate plan, next candle OPEN and simulated
    *previously realized* balance/positions. Later modeled exits are scheduled
    for their candle CLOSE, never credited when a future price is first read.
    A path with UNKNOWN/OPEN outcome retains reserved risk until the study ends,
    rather than silently freeing capital or inventing realized PnL.
    """
    ordered = _valid(candidates, horizons)
    summary = {}
    for minutes in horizons:
        ledgers = {coin: {"equity": INITIAL_EACH,
                          "day_start": INITIAL_EACH,
                          "day": None} for coin in COINS}
        positions = {}
        events = []
        max_used_margin = Decimal("0")
        max_reserved_risk = Decimal("0")

        def total_equity():
            return sum((s["equity"] for s in ledgers.values()), Decimal("0"))

        def roll_day(at):
            day = _day(at)
            for state in ledgers.values():
                if state["day"] != day:
                    state["day"] = day
                    state["day_start"] = state["equity"]

        def usage():
            used = sum((x["margin"] for x in positions.values()), Decimal("0"))
            reserved = sum((x["risk"] for x in positions.values()), Decimal("0"))
            return used, reserved

        def note_usage():
            nonlocal max_used_margin, max_reserved_risk
            used, reserved = usage()
            max_used_margin = max(max_used_margin, used)
            max_reserved_risk = max(max_reserved_risk, reserved)
            # No pooled 150 USDT spending, even as the hypothetical equity
            # changes after previously closed trades.
            if used > total_equity():
                raise ValueError("portfolio_margin_invariant_failed")
            if any(x["margin"] > ledgers[c]["equity"]
                   for c, x in positions.items()):
                raise ValueError("per_coin_margin_invariant_failed")

        def release_before(at):
            completed = sorted(
                ((coin, state) for coin, state in positions.items()
                 if state["exit_at"] is not None and state["exit_at"] <= at),
                key=lambda item: (item[1]["exit_at"], item[0]))
            for coin, state in completed:
                roll_day(state["exit_at"])
                ledgers[coin]["equity"] += state["pnl"]
                # A loss exceeding the modeled stop/fees is possible during
                # gaps. No new positions are accepted if equity is exhausted.
                events.append({"symbol": coin, "status": "CLOSED_RESEARCH_ONLY",
                               "exit_reason": state["exit_reason"],
                               "exit_at_ms": state["exit_at"],
                               "net_pnl_excluding_funding": str(state["pnl"]),
                               "orders_sent": False})
                del positions[coin]
            note_usage()

        for record in ordered:
            symbol = record["symbol"]
            coin = symbol.split("/")[0]
            open_at = record["signal_candle_open_ms"] + STEP_MS
            release_before(open_at)
            roll_day(open_at)
            basic = {"symbol": coin,
                     "signal_candle_open_ms": record["signal_candle_open_ms"],
                     "entry_at_ms": open_at, "orders_sent": False}
            if coin in positions:
                events.append({**basic, "status": "BLOCKED_RESEARCH_ONLY",
                               "reason": "symbol_position_already_open"})
                continue

            used_margin, reserved_risk = usage()
            eq = ledgers[coin]["equity"]
            if eq <= 0 or total_equity() <= 0:
                events.append({**basic, "status": "BLOCKED_RESEARCH_ONLY",
                               "reason": "equity_exhausted"})
                continue
            free_coin_margin = eq
            free_portfolio_margin = max(
                Decimal("0"), total_equity() - used_margin)
            available_margin = min(free_coin_margin, free_portfolio_margin)

            outcome = study_resized_horizons(
                record["plan"], record["candles"],
                signal_candle_open_ms=record["signal_candle_open_ms"],
                as_of_ms=record["as_of_ms"],
                amount_step=record["exchange_limits"]["amount_step"],
                min_amount=record["exchange_limits"]["min_amount"],
                min_notional=record["exchange_limits"]["min_notional"],
                paper_equity=str(eq),
                day_start_equity=str(ledgers[coin]["day_start"]),
                available_margin=str(available_margin),
                portfolio_equity=str(total_equity()),
                portfolio_day_start_equity=str(sum(
                    (s["day_start"] for s in ledgers.values()), Decimal("0"))),
                portfolio_open_risk=str(reserved_risk),
                horizons=(minutes,),
                fee_rate=fee_rate, slippage_rate=slippage_rate)

            if outcome["status"] != "OFFLINE_RESIZED_HORIZON_STUDY":
                events.append({**basic, "status": outcome["status"],
                               "reason": outcome.get("reason", "unknown")})
                continue
            sizing = outcome["sizing"]
            replay = outcome["results"][str(minutes)]
            if replay["status"] == "REJECTED":
                events.append({**basic, "status": "BLOCKED_RESEARCH_ONLY",
                               "reason": replay.get("reason", "replay_rejected")})
                continue
            margin = Decimal(sizing["estimated_margin_usdt"])
            risk = Decimal(sizing["estimated_stop_risk_usdt"])
            if not (margin > 0 and risk > 0 and
                    margin <= available_margin and
                    risk <= Decimal("1.50")):
                raise ValueError("unsafe_portfolio_sizing")
            exit_at = None
            pnl = Decimal("0")
            exit_reason = None
            if replay["status"] == "CLOSED_HYPOTHETICAL":
                exit_at = replay["exit_candle_ms"] + STEP_MS
                if exit_at <= open_at:
                    raise ValueError("exit_before_entry")
                pnl = Decimal(replay["net_pnl_excluding_funding"])
                if not pnl.is_finite():
                    raise ValueError("invalid_simulated_pnl")
                exit_reason = replay["exit_reason"]
            elif replay["status"] not in ("OPEN_HYPOTHETICAL", "UNKNOWN"):
                raise ValueError("unsupported_replay_status")
            positions[coin] = {"margin": margin, "risk": risk,
                               "exit_at": exit_at, "pnl": pnl,
                               "exit_reason": exit_reason}
            events.append({**basic, "status": "OPENED_RESEARCH_ONLY",
                           "quantity": sizing["research_quantity"],
                           "modeled_margin": str(margin),
                           "modeled_stop_risk": str(risk),
                           "eventual_outcome": replay["status"]})
            note_usage()

        # At finalization, only exits supported by closed historical bars are
        # recognized. Unknown/open positions remain reserved, not profitable.
        future_exits = [p["exit_at"] for p in positions.values()
                        if p["exit_at"] is not None]
        if future_exits:
            release_before(max(future_exits))
        remaining = {coin: {"margin": str(x["margin"]),
                            "risk": str(x["risk"]),
                            "outcome": "UNRESOLVED_RESEARCH_ONLY"}
                     for coin, x in positions.items()}
        closed = [e for e in events if e["status"] == "CLOSED_RESEARCH_ONLY"]
        realized_pnl = sum(
            (Decimal(e["net_pnl_excluding_funding"]) for e in closed),
            Decimal("0"))
        if total_equity() != INITIAL_TOTAL + realized_pnl:
            raise ValueError("portfolio_equity_reconciliation_failed")
        summary[str(minutes)] = {
            "initial_equity": str(INITIAL_TOTAL),
            "final_realized_equity": str(total_equity()),
            "realized_pnl_excluding_funding": str(realized_pnl),
            "closed": len(closed),
            "modeled_wins": sum(
                Decimal(e["net_pnl_excluding_funding"]) > 0 for e in closed),
            "max_used_margin": str(max_used_margin),
            "max_reserved_risk": str(max_reserved_risk),
            "coin_balances": {
                c: str(ledgers[c]["equity"]) for c in COINS},
            "unresolved_positions": remaining,
            "events": events
        }
    return {
        "status": "OFFLINE_FOUR_COIN_PORTFOLIO_ONLY",
        "orders_sent": False,
        "execution_authorized": False,
        "live_trading_enabled": False,
        "horizons_minutes": list(horizons),
        "results": summary,
        "funding_included": False,
        "actual_fills_verified": False,
        "decision_tie_break": "signal_time_then_symbol_lexical",
        "risk_model": "realized-only, per-coin 37.50 USDT; no mark-to-market",
    }
