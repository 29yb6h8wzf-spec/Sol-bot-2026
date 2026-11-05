"""End-to-end offline tests: research sizing and 15/30/60/90m exits.

Only synthetic public-market-shaped OHLC fixtures. Never send or plan orders.
"""
from copy import deepcopy
from decimal import Decimal as D
import pytest

from futures_engine.offline_resized_horizon_study import (
    study_resized_horizons,
)

T = 1793738100000
STEP = 300000


def plan(**updates):
    p = {
        "status": "INDICATIVE_PLAN_ONLY_NOT_EXECUTABLE",
        "orders_sent": False, "execution_authorized": False,
        "risk_snapshot_approved": False, "side": "short",
        "entry": "100", "stop": "101", "target": "98",
        "quantity": "2", "closed_5m_candle_ms": T
    }
    p.update(updates)
    return p


def bars(n=18):
    data = []
    for i in range(n):
        opening = 100.2 - i * 0.01
        data.append((T + STEP * (i + 1), opening, opening + 0.2,
                     opening - 0.2, opening - 0.05))
    return data


def study(p=None, history=None, **updates):
    candles = history if history is not None else bars(18)
    inputs = dict(
        signal_candle_open_ms=T,
        as_of_ms=candles[-1][0] + STEP if candles else T + STEP,
        amount_step="0.01", min_amount="0.01", min_notional="5",
        paper_equity="37.50", day_start_equity="37.50",
        available_margin="37.50", portfolio_equity="150",
        portfolio_day_start_equity="150", portfolio_open_risk="0",
    )
    inputs.update(updates)
    return study_resized_horizons(p or plan(), candles, **inputs)


def test_full_15_to_90_research_study_without_mutation_or_execution():
    archived = plan()
    original = deepcopy(archived)
    candle_history = bars()
    historical_copy = deepcopy(candle_history)
    result = study(archived, candle_history)
    assert result["status"] == "OFFLINE_RESIZED_HORIZON_STUDY"
    assert result["orders_sent"] is False
    assert result["execution_authorized"] is False
    assert result["actual_fills_verified"] is False
    assert result["funding_included"] is False
    assert result["first_possible_entry_candle_open_ms"] == T + STEP
    assert result["horizons_minutes"] == [15, 30, 60, 90]
    assert set(result["results"]) == {"15", "30", "60", "90"}
    assert all(x["status"] == "CLOSED_HYPOTHETICAL"
               for x in result["results"].values())
    assert all(x["exit_reason"] == "TIME_LIMIT"
               for x in result["results"].values())
    assert all(x["orders_sent"] is False
               for x in result["results"].values())
    assert archived == original and candle_history == historical_copy


def test_resizing_reduces_original_qty_and_stays_within_per_coin_risk():
    result = study()
    s = result["sizing"]
    assert D("0") < D(s["research_quantity"]) < D("2")
    assert D(s["estimated_stop_risk_usdt"]) <= D("0.375")
    assert D(s["estimated_margin_usdt"]) <= D("37.50")
    assert D(s["notional_usdt"]) <= D("75")


def test_different_max_holding_durations_have_different_outcomes():
    result = study()
    pnl_15 = D(result["results"]["15"]["net_pnl_excluding_funding"])
    pnl_90 = D(result["results"]["90"]["net_pnl_excluding_funding"])
    assert pnl_90 > pnl_15


def test_stop_hit_before_90_minutes_exits_at_stop():
    candles = bars()
    start = candles[2]
    candles[2] = (start[0], start[1], 101.5, start[2], start[4])
    result = study(history=candles)
    assert result["results"]["90"]["exit_reason"] == "STOP"
    assert result["results"]["90"]["exit_candle_ms"] == T + 3 * STEP
    assert D(result["results"]["90"]["net_pnl_excluding_funding"]) < 0


def test_target_hit_after_15_but_before_90_minute_limit():
    candles = bars()
    item = candles[5]
    candles[5] = (item[0], item[1], item[2], 97.5, 98.0)
    result = study(history=candles)
    assert result["results"]["15"]["exit_reason"] == "TIME_LIMIT"
    assert result["results"]["30"]["exit_reason"] == "TARGET"
    assert result["results"]["60"]["exit_reason"] == "TARGET"
    assert result["results"]["90"]["exit_reason"] == "TARGET"


def test_both_brackets_touched_same_candle_prefers_stop():
    candles = bars()
    opening = candles[2][1]
    candles[2] = (candles[2][0], opening, 101.5, 97.5, 99.0)
    result = study(history=candles)
    assert result["results"]["90"]["exit_reason"] == "STOP"


def test_duplicate_or_gap_in_history_not_a_realized_profit():
    candles = bars()
    del candles[6]
    result = study(history=candles)
    assert result["results"]["90"]["status"] == "UNKNOWN"
    assert "net_pnl_excluding_funding" not in result["results"]["90"]


def test_only_partial_90_minute_history_is_not_marked_closed():
    result = study(history=bars(17))
    assert result["results"]["90"]["status"] == "OPEN_HYPOTHETICAL"
    assert "net_pnl_excluding_funding" not in result["results"]["90"]


def test_unclosed_latest_bar_is_not_usable():
    candles = bars()
    result = study(history=candles, as_of_ms=candles[-1][0] + STEP - 1)
    assert result["status"] == "UNKNOWN_RESEARCH_ONLY"
    assert result["reason"] == "unclosed_or_invalid_future_candle"
    assert "results" not in result


def test_signal_candle_cannot_be_replayed_as_entry_candle():
    candles = bars()
    candles[0] = (T, 100, 100.3, 99.7, 100)
    result = study(history=candles)
    assert result["status"] == "UNKNOWN_RESEARCH_ONLY"
    assert result["reason"] == "missing_first_eligible_candle"


def test_rejected_plan_with_missing_data_never_generates_orders():
    result = study(history=[])
    assert result["status"] == "UNKNOWN_RESEARCH_ONLY"
    assert result["orders_sent"] is False
    assert "results" not in result


def test_exchange_dust_causes_rejection_instead_of_forcing_minimum():
    btc = plan(entry="79000", stop="79200", target="78600",
               quantity="0.003")
    data = [(T + STEP, 79000, 79020, 78980, 79000)]
    result = study(btc, data, amount_step="0.001",
                   min_amount="0.001", min_notional="5")
    assert result["status"] == "REJECTED_RESEARCH_ONLY"
    assert result["reason"] == "exchange_minimum_or_dust"
    assert "results" not in result


def test_daily_loss_guard_stops_sensitivity_without_replay():
    result = study(paper_equity="35.60", day_start_equity="37.50",
                   available_margin="35.60")
    assert result["status"] == "REJECTED_RESEARCH_ONLY"
    assert result["reason"] == "daily_loss_limit"


def test_reserved_portfolio_risk_cannot_be_ignored():
    result = study(portfolio_open_risk="7.50")
    assert result["status"] == "REJECTED_RESEARCH_ONLY"
    assert result["reason"] == "no_risk_or_margin_budget"


def test_not_allowing_unverified_150_allocation_as_37_5_margin():
    with pytest.raises(ValueError, match="unverified_available_margin"):
        study(available_margin="150")


@pytest.mark.parametrize("authorization", [
    {"orders_sent": True},
    {"execution_authorized": True},
    {"risk_snapshot_approved": True},
])
def test_bypassed_execution_guard_never_reaches_sizing(authorization):
    with pytest.raises(ValueError, match="non_executable_plan_required"):
        study(plan(**authorization))


def test_wrong_plan_candle_timestamp_rejected():
    with pytest.raises(ValueError, match="research_plan_timestamp_mismatch"):
        study(plan(), signal_candle_open_ms=T + STEP)


def test_90_minute_comparison_is_available_only_with_safe_plan():
    result = study()
    assert result["status"] == "OFFLINE_RESIZED_HORIZON_STUDY"
    assert "90" in result["results"]
    assert D(result["sizing"]["estimated_stop_risk_usdt"]) <= D("1.50")
