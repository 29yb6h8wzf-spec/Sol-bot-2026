"""Deterministic four-asset scenario: synthetic data; absolutely no orders."""
from copy import deepcopy
from decimal import Decimal as D

import pytest

from futures_engine.offline_four_coin_portfolio import (
    SYMBOLS, STEP_MS, compare_four_coin_horizons, simulate_one_day
)

T = 1793738100000
LIMITS = {symbol: {"amount_step": "0.01", "min_amount": "0.01",
                   "min_notional": "5"} for symbol in SYMBOLS}


def plan(t=T, **extra):
    result = {"status": "INDICATIVE_PLAN_ONLY_NOT_EXECUTABLE",
              "orders_sent": False, "execution_authorized": False,
              "risk_snapshot_approved": False, "side": "short",
              "entry": "100", "stop": "101", "target": "98",
              "quantity": "2", "closed_5m_candle_ms": t}
    result.update(extra)
    return result


def bars(t=T, n=18, *, stop_at=None, target_at=None):
    result = []
    for i in range(n):
        opening = D("100") - D("0.05") * i
        close = opening - D("0.01")
        high = opening + D("0.2")
        low = close - D("0.2")
        if i == stop_at:
            high = D("102")
        if i == target_at:
            low = D("97.5")
        result.append((t + (i + 1)*STEP_MS,
                       str(opening), str(high), str(low), str(close)))
    return result


def candidate(symbol, t=T, sid=None, history=None):
    return {
        "symbol": symbol,
        "signal_id": sid or (symbol + "-" + str(t)),
        "signal_candle_open_ms": t,
        "plan": plan(t),
        "candles": history if history is not None else bars(t),
    }


def run(records, *, horizon=90, as_of=None, **other):
    return simulate_one_day(
        records, horizon_minutes=horizon,
        as_of_ms=as_of if as_of is not None else T+20*STEP_MS,
        market_limits=LIMITS, **other)


def events(scenario, kind):
    return [item for item in scenario["events"] if item["event"] == kind]


def test_four_simultaneous_assets_use_separate_37_5_ledger():
    inputs = [candidate(symbol) for symbol in SYMBOLS]
    unmodified = deepcopy(inputs)
    out = run(inputs)
    assert out["status"] == "OFFLINE_FOUR_COIN_PORTFOLIO_STUDY"
    assert out["orders_sent"] is False and out["execution_authorized"] is False
    assert out["initial_total_usdt"] == "150.00"
    assert out["closed_hypothetical_count"] == 4
    assert len(events(out, "ACCEPTED_RESEARCH_ONLY")) == 4
    assert len(events(out, "CLOSED_HYPOTHETICAL")) == 4
    assert D(out["max_concurrent_reserved_risk_usdt"]) <= D("1.50")
    assert D(out["max_concurrent_reserved_margin_usdt"]) <= D("150")
    assert len({item["symbol"] for item in events(out, "ACCEPTED_RESEARCH_ONLY")}) == 4
    for item in events(out, "ACCEPTED_RESEARCH_ONLY"):
        assert D(item["reserved_risk_usdt"]) <= D("0.375")
        assert D(item["reserved_margin_usdt"]) <= D("37.50")
    assert inputs == unmodified
    assert all(item["orders_sent"] is False for item in out["events"])


def test_same_coin_overlapping_signal_rejected_without_second_position():
    shared = bars(n=20)
    inputs = [candidate("BTC", history=shared[:18]),
              candidate("BTC", T+STEP_MS, history=shared[1:19])]
    out = run(inputs)
    assert len(events(out, "ACCEPTED_RESEARCH_ONLY")) == 1
    assert len(events(out, "SKIPPED_RESEARCH_ONLY")) == 1
    assert events(out, "SKIPPED_RESEARCH_ONLY")[0]["reason"] == (
        "overlapping_same_symbol_position")
    assert out["closed_hypothetical_count"] == 1


def test_money_and_margin_released_only_after_stop_candle_closes():
    shared = bars(n=21, stop_at=1)
    primary = candidate("BTC", history=shared[:18])
    # Stop occurs on candle starting T + 2*STEP, so risk frees
    # only at T + 3*STEP. The first replacement entry occurs earlier.
    early = candidate("BTC", T+STEP_MS, sid="too-early", history=shared[1:19])
    later = candidate("BTC", T+2*STEP_MS, sid="after-close",
                      history=shared[2:20])
    # All replacement candles must be fully closed before this retrospective replay.
    out = run([primary, early, later], as_of=T+24*STEP_MS)
    assert len(events(out, "SKIPPED_RESEARCH_ONLY")) == 1
    assert len(events(out, "ACCEPTED_RESEARCH_ONLY")) == 2
    closes = events(out, "CLOSED_HYPOTHETICAL")
    assert any(x["exit_reason"] == "STOP" for x in closes)
    assert any(x["at_ms"] == T+3*STEP_MS for x in closes)
    assert out["closed_hypothetical_count"] >= 1


def test_same_timestamp_arrivals_have_deterministic_symbol_order():
    a = [candidate("XRP"), candidate("ETH"), candidate("BTC"),
         candidate("SOL")]
    b = list(reversed(a))
    left = run(a)
    right = run(b)
    assert left == right
    assert [x["symbol"] for x in events(left, "ACCEPTED_RESEARCH_ONLY")] == [
        "BTC", "ETH", "SOL", "XRP"]


@pytest.mark.parametrize("minutes", [15, 30, 60, 90])
def test_all_four_coins_supported_at_every_requested_horizon(minutes):
    r = run([candidate(s) for s in SYMBOLS], horizon=minutes)
    assert r["horizon_minutes"] == minutes
    assert len(events(r, "ACCEPTED_RESEARCH_ONLY")) == 4
    assert r["closed_hypothetical_count"] == 4


def test_four_portfolio_horizons_start_from_same_initial_equity():
    records = [candidate(s) for s in SYMBOLS]
    result = compare_four_coin_horizons(
        records, as_of_ms=T+20*STEP_MS, market_limits=LIMITS)
    assert result["status"] == "OFFLINE_PORTFOLIO_HORIZON_COMPARISON"
    assert result["orders_sent"] is False
    assert set(result["outcomes"]) == {"15", "30", "60", "90"}
    for scenario in result["outcomes"].values():
        assert scenario["initial_total_usdt"] == "150.00"
        assert scenario["closed_hypothetical_count"] == 4


def test_unfinished_horizon_never_credits_unrealized_profit():
    out = run([candidate("SOL", history=bars(n=6))],
              as_of=T+7*STEP_MS)
    assert out["closed_hypothetical_count"] == 0
    assert D(out["closed_net_pnl_excluding_funding_usdt"]) == 0
    assert out["unresolved_positions"] == ["SOL"]
    assert D(out["end_reserved_risk_usdt"]) > 0


def test_missing_candle_data_cannot_generate_realized_profit():
    sample = bars()
    del sample[6]
    out = run([candidate("SOL", history=sample)])
    assert out["closed_hypothetical_count"] == 0
    assert out["unresolved_positions"] == ["SOL"]


def test_ledger_dust_rejected_instead_of_borrowing_other_coins_equity():
    btc = candidate("BTC")
    btc["plan"] = plan(entry="79000", stop="79200", target="78600",
                       quantity="0.003")
    btc["candles"] = [(T+STEP_MS, "79000", "79020", "78980", "79000")]
    limits = deepcopy(LIMITS)
    limits["BTC"] = {"amount_step": "0.001", "min_amount": "0.001",
                     "min_notional": "5"}
    out = simulate_one_day([btc], horizon_minutes=15,
                           as_of_ms=T+3*STEP_MS,
                           market_limits=limits)
    rejected = events(out, "REJECTED_RESEARCH_ONLY")
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "exchange_minimum_or_dust"
    assert out["closed_hypothetical_count"] == 0


def test_no_execution_permission_even_if_plan_flag_manipulated():
    source = candidate("BTC")
    source["plan"]["execution_authorized"] = True
    with pytest.raises(ValueError, match="non_executable_plan_required"):
        run([source])


def test_duplicate_signal_identity_is_rejected_before_replay():
    with pytest.raises(ValueError, match="duplicate_signal_id"):
        run([candidate("BTC"), candidate("ETH", sid="BTC-"+str(T))])


def test_cross_utc_day_horizon_rejected_instead_of_resetting_risk():
    # Research candle at 23:00 UTC. The 90m window would cross midnight.
    at = 1793833200000
    item = candidate("BTC", t=at, history=bars(at))
    result = simulate_one_day(
        [item], horizon_minutes=90,
        as_of_ms=at+21*STEP_MS, market_limits=LIMITS)
    assert len(events(result, "SKIPPED_RESEARCH_ONLY")) == 1
    assert events(result, "SKIPPED_RESEARCH_ONLY")[0]["reason"] == (
        "horizon_crosses_utc_day")


def test_invalid_assumed_account_allocation_is_rejected():
    with pytest.raises(ValueError, match="initial_paper_allocation_exceeds_ledger"):
        run([candidate("BTC")], initial_equity_per_coin="150")


def test_unknown_exchange_limits_fail_closed():
    partial = {s: LIMITS[s] for s in ("BTC", "ETH", "SOL")}
    with pytest.raises(ValueError, match="four_explicit_market_limits_required"):
        simulate_one_day([candidate("BTC")], horizon_minutes=90,
                         as_of_ms=T+20*STEP_MS, market_limits=partial)


def test_multi_day_input_not_silently_merged_into_one_daily_limit():
    next_day = candidate("ETH", T + 288 * STEP_MS)
    with pytest.raises(ValueError, match="multi_day_portfolio_requires_separate_daily_runs"):
        run([candidate("BTC"), next_day],
            as_of=T+310*STEP_MS)


@pytest.mark.parametrize("bad_horizon", [0, 5, 105, 90.0, True, "90"])
def test_unsupported_horizons_fail_closed(bad_horizon):
    with pytest.raises(ValueError, match="unsupported_research_horizon"):
        run([], horizon=bad_horizon)


def test_account_results_not_reported_as_actual_fills_or_funding_complete():
    result = run([candidate("XRP")])
    assert result["actual_fills_verified"] is False
    assert result["funding_included"] is False
    assert result["orders_sent"] is False

def test_conflicting_same_coin_ohlc_at_identical_time_fails_closed():
    shared = bars(n=20)
    first = candidate("BTC", history=shared[:18])
    second = candidate("BTC", T+STEP_MS, sid="conflicting-snapshot",
                       history=list(shared[1:19]))
    bar = second["candles"][0]
    # Both are individually valid OHLC candles with the SAME timestamp.
    # Changing only the second signal's open must not be accepted.
    second["candles"][0] = (bar[0], "99.96", bar[2], bar[3], bar[4])
    with pytest.raises(ValueError, match="conflicting_symbol_candle_history"):
        run([first, second])


def test_matching_overlaps_allow_equivalent_numeric_representations():
    shared = bars(n=20)
    first = candidate("BTC", history=shared[:18])
    second = candidate("BTC", T+STEP_MS, sid="equivalent-format",
                       history=list(shared[1:19]))
    bar = second["candles"][0]
    second["candles"][0] = (bar[0], "99.9500", bar[2], bar[3], bar[4])
    out = run([first, second])
    assert len(events(out, "ACCEPTED_RESEARCH_ONLY")) == 1
    assert len(events(out, "SKIPPED_RESEARCH_ONLY")) == 1


def test_conflicting_history_rejected_even_if_second_trade_would_be_skipped():
    shared = bars(n=20)
    first = candidate("SOL", history=shared[:18])
    second = candidate("SOL", T+STEP_MS, sid="overlapping-skipped",
                       history=list(shared[1:19]))
    bar = second["candles"][2]
    second["candles"][2] = (bar[0], bar[1], "100.40", bar[3], bar[4])
    with pytest.raises(ValueError, match="conflicting_symbol_candle_history"):
        run([first, second])


def test_invalid_ohlc_from_skipped_candidate_still_fails_closed():
    shared = bars(n=20)
    first = candidate("XRP", history=shared[:18])
    second = candidate("XRP", T+STEP_MS, sid="invalid-skipped",
                       history=list(shared[1:19]))
    bar = second["candles"][0]
    second["candles"][0] = (bar[0], bar[1], "NaN", bar[3], bar[4])
    with pytest.raises(ValueError, match="invalid_portfolio_candle"):
        run([first, second])
