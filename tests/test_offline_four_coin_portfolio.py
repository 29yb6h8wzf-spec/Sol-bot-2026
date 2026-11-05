"""Four-coin retrospective portfolio accounting, not actual orders/trading."""
from copy import deepcopy
from decimal import Decimal as D

import pytest

from futures_engine.offline_four_coin_portfolio import simulate_portfolio

T = 1793738100000
STEP = 300000
COINS = ("BTC", "ETH", "SOL", "XRP")


def candidate(coin="SOL", signal=T, *, n=18, bars=None, plan_changes=None,
              limits=None, as_of_ms=None):
    sym = f"{coin}/USDT:USDT"
    p = {"status": "INDICATIVE_PLAN_ONLY_NOT_EXECUTABLE",
         "orders_sent": False, "execution_authorized": False,
         "risk_snapshot_approved": False,
         "symbol": sym, "side": "short",
         "entry": "100", "stop": "101", "target": "98",
         "quantity": "2", "closed_5m_candle_ms": signal}
    p.update(plan_changes or {})
    if bars is None:
        bars = []
        for i in range(n):
            op = 100.2 - i * 0.01
            bars.append((signal + (i+1)*STEP, op, op+0.2, op-0.2,
                         op-0.05))
    return {"symbol": sym, "signal_candle_open_ms": signal,
            "plan": p, "candles": bars,
            "exchange_limits": limits or {
                "amount_step": "0.01", "min_amount": "0.01",
                "min_notional": "5"},
            "as_of_ms": as_of_ms if as_of_ms is not None else (
                bars[-1][0]+STEP if bars else signal+STEP)}


def test_all_four_simultaneous_signals_share_only_150_not_extra_margin():
    records = [candidate(c) for c in COINS]
    before = deepcopy(records)
    model = simulate_portfolio(records)
    assert model["status"] == "OFFLINE_FOUR_COIN_PORTFOLIO_ONLY"
    assert model["orders_sent"] is False
    assert model["execution_authorized"] is False
    assert model["funding_included"] is False
    for horizon in ("15", "30", "60", "90"):
        r = model["results"][horizon]
        assert sum(e["status"] == "OPENED_RESEARCH_ONLY" for e in r["events"]) == 4
        assert r["closed"] == 4
        assert D(r["max_used_margin"]) <= D("150")
        assert D(r["max_reserved_risk"]) <= D("1.50")
        assert set(r["coin_balances"]) == set(COINS)
        assert not r["unresolved_positions"]
        assert D(r["final_realized_equity"]) == (
            D("150") + D(r["realized_pnl_excluding_funding"]))
        opens = [e for e in r["events"]
                 if e["status"] == "OPENED_RESEARCH_ONLY"]
        assert all(D(e["modeled_stop_risk"]) <= D("0.375")
                   for e in opens)
        assert all(D(e["modeled_margin"]) <= D("37.50")
                   for e in opens)
    assert records == before


def test_simultaneous_tie_break_is_stable_regardless_of_input_order():
    original = [candidate(c) for c in COINS]
    a = simulate_portfolio(original, horizons=(90,))
    b = simulate_portfolio(list(reversed(original)), horizons=(90,))
    assert a == b
    assert [e["symbol"] for e in a["results"]["90"]["events"][:4]] == (
        ["BTC", "ETH", "SOL", "XRP"])


def test_second_signal_same_coin_does_not_reuse_open_margin():
    a = candidate("SOL", signal=T)
    b = candidate("SOL", signal=T+STEP)
    r = simulate_portfolio([a, b], horizons=(90,))["results"]["90"]
    assert sum(e["status"] == "OPENED_RESEARCH_ONLY"
               for e in r["events"]) == 1
    assert sum(e.get("reason") == "symbol_position_already_open"
               for e in r["events"]) == 1
    assert r["closed"] == 1


def test_same_coin_may_reenter_only_after_previous_exit_is_closed():
    first = candidate("ETH", signal=T, n=3)
    later = candidate("ETH", signal=T+4*STEP, n=3)
    r = simulate_portfolio([first, later], horizons=(15,))["results"]["15"]
    assert sum(e["status"] == "OPENED_RESEARCH_ONLY"
               for e in r["events"]) == 2
    assert r["closed"] == 2
    closed = [e for e in r["events"]
              if e["status"] == "CLOSED_RESEARCH_ONLY"]
    assert closed[0]["exit_at_ms"] == T+4*STEP
    assert closed[1]["exit_at_ms"] == T+8*STEP


def test_90_minute_holding_exposes_more_research_pnl_than_15():
    r = simulate_portfolio([candidate("XRP")])["results"]
    a = D(r["15"]["realized_pnl_excluding_funding"])
    b = D(r["90"]["realized_pnl_excluding_funding"])
    assert b > a


def test_btc_min_quantity_does_not_force_extra_margin():
    btc = candidate(
        "BTC", plan_changes={
            "entry": "79000", "stop": "79200",
            "target": "78600", "quantity": "0.003"},
        bars=[(T+STEP, 79000, 79020, 78980, 79000)],
        limits={"amount_step": "0.001", "min_amount": "0.001",
                "min_notional": "5"})
    r = simulate_portfolio([btc], horizons=(15,))["results"]["15"]
    assert any(e.get("reason") == "exchange_minimum_or_dust"
               for e in r["events"])
    assert r["closed"] == 0
    assert D(r["final_realized_equity"]) == D("150")
    assert D(r["max_used_margin"]) == D("0")


def test_stop_and_target_same_candle_consistently_choose_stop():
    item = candidate("BTC")
    bars = list(item["candles"])
    original = bars[2]
    bars[2] = (original[0], original[1], 101.5, 97.5, 99)
    item["candles"] = bars
    r = simulate_portfolio([item], horizons=(90,))["results"]["90"]
    assert r["closed"] == 1
    exits = [x for x in r["events"]
             if x["status"] == "CLOSED_RESEARCH_ONLY"]
    assert exits[0]["exit_reason"] == "STOP"
    assert D(exits[0]["net_pnl_excluding_funding"]) < 0


def test_missing_future_candles_never_realize_profit_or_free_margin():
    one = candidate("SOL", n=17)
    second = candidate("SOL", signal=T+2*STEP)
    r = simulate_portfolio([one, second], horizons=(90,))["results"]["90"]
    assert r["closed"] == 0
    assert "SOL" in r["unresolved_positions"]
    assert D(r["final_realized_equity"]) == D("150")
    assert any(e.get("reason") == "symbol_position_already_open"
               for e in r["events"])
    assert D(r["max_used_margin"]) > 0


def test_gap_between_candles_does_not_generate_hypothetical_profit():
    one = candidate("XRP")
    candles = list(one["candles"])
    del candles[5]
    one["candles"] = candles
    two = candidate("XRP", signal=T+2*STEP)
    r = simulate_portfolio([one, two], horizons=(90,))["results"]["90"]
    assert r["closed"] == 0
    assert "XRP" in r["unresolved_positions"]
    assert any(e.get("reason") == "symbol_position_already_open"
               for e in r["events"])


def test_research_plan_cannot_consume_unclosed_candle():
    one = candidate("BTC")
    one["as_of_ms"] = one["candles"][-1][0] + STEP - 1
    r = simulate_portfolio([one], horizons=(90,))["results"]["90"]
    assert r["closed"] == 0
    assert r["events"][0]["status"] == "UNKNOWN_RESEARCH_ONLY"
    assert D(r["max_used_margin"]) == 0


def test_risk_sizing_has_no_order_capabilities_or_side_effects():
    model = simulate_portfolio([candidate("SOL")], horizons=(90,))
    assert model["live_trading_enabled"] is False
    assert model["orders_sent"] is False
    assert model["actual_fills_verified"] is False
    assert all(e["orders_sent"] is False
               for e in model["results"]["90"]["events"])


def test_invalid_signal_candle_or_unsupported_symbol_is_rejected():
    first = candidate()
    first["signal_candle_open_ms"] += 1
    with pytest.raises(ValueError, match="invalid_signal_candle"):
        simulate_portfolio([first])
    second = candidate()
    second["symbol"] = "DOGE/USDT:USDT"
    with pytest.raises(ValueError, match="unsupported_symbol"):
        simulate_portfolio([second])


def test_duplicate_symbol_candle_not_counted_twice():
    p = candidate("BTC")
    with pytest.raises(ValueError, match="duplicate_symbol_candle"):
        simulate_portfolio([p, deepcopy(p)])


def test_invalid_or_duplicate_horizons_fail_closed():
    with pytest.raises(ValueError, match="invalid_horizon_minutes"):
        simulate_portfolio([candidate()], horizons=(13,))
    with pytest.raises(ValueError, match="duplicate_horizons"):
        simulate_portfolio([candidate()], horizons=(90, 90))


def test_executable_plan_is_never_admitted_to_portfolio():
    p = candidate("ETH", plan_changes={"execution_authorized": True})
    with pytest.raises(ValueError, match="non_executable_plan_required"):
        simulate_portfolio([p], horizons=(90,))
