"""Conservative, deterministic long-horizon study without orders."""
import pytest
from futures_engine.offline_plan_replay import replay
from futures_engine.offline_horizon_comparison import compare, compare_research_open_time

T=1793738100000

def plan(**changes):
    p={"status":"INDICATIVE_PLAN_ONLY_NOT_EXECUTABLE",
       "orders_sent":False, "execution_authorized":False,
       "risk_snapshot_approved":False, "side":"long",
       "entry":"100", "stop":"99", "target":"102", "quantity":"1",
       "closed_5m_candle_ms":T}
    p.update(changes)
    return p

def flat(n, *, close=100.3):
    return [(T+i*300000, 100 if i==0 else close,
             max(100,close)+0.1, min(100,close)-0.1,close)
            for i in range(n)]

@pytest.mark.parametrize("minutes", [15,30,60,90])
def test_exits_at_end_of_completed_candle_not_at_entry(minutes):
    candles=flat(minutes//5)
    r=replay(plan(),candles,fee_rate="0.0006",
             slippage_rate="0.0005",max_holding_minutes=minutes)
    assert r["status"]=="CLOSED_HYPOTHETICAL"
    assert r["exit_reason"]=="TIME_LIMIT"
    assert r["exit_candle_ms"]==T+(minutes//5-1)*300000
    assert r["orders_sent"] is False
    assert "net_pnl_excluding_funding" in r

@pytest.mark.parametrize("minutes", [15,30,60,90])
def test_horizon_not_mature_without_all_closed_candles(minutes):
    r=replay(plan(),flat(minutes//5-1),
             max_holding_minutes=minutes)
    assert r["status"]=="OPEN_HYPOTHETICAL"
    assert "net_pnl_excluding_funding" not in r

def test_brackets_take_priority_over_time_limit():
    candles=[(T,100,103,98,100)]+flat(18)[1:]
    r=compare(plan(),candles)
    assert set(r["results"])=={"15","30","60","90"}
    assert all(x["exit_reason"]=="STOP" for x in r["results"].values())

def test_target_before_90_minute_limit():
    candles=flat(17)+[(T+17*300000,100,102.3,99.9,102)]
    r=compare(plan(),candles)
    assert r["results"]["15"]["exit_reason"]=="TIME_LIMIT"
    assert r["results"]["90"]["exit_reason"]=="TARGET"

def test_90_minute_return_can_differ_from_15_minute_return():
    bars=[]
    for i in range(18):
        close=100+0.04*i
        bars.append((T+i*300000,close,close+0.06,close-0.06,close))
    result=compare(plan(),bars)
    p15=float(result["results"]["15"]["net_pnl_excluding_funding"])
    p90=float(result["results"]["90"]["net_pnl_excluding_funding"])
    assert p90>p15
    assert result["orders_sent"] is False

def test_short_time_limit_uses_adverse_exit_slippage():
    p=plan(side="short",stop="101",target="98")
    bars=[(T+i*300000,100,100.2,99.8,100) for i in range(18)]
    r=replay(p,bars,max_holding_minutes=90,
             slippage_rate="0.0005",fee_rate="0.0006")
    assert r["exit_reason"]=="TIME_LIMIT"
    assert float(r["exit_fill"])>100
    assert float(r["net_pnl_excluding_funding"])<0

@pytest.mark.parametrize("limit", [-15,0,1,7,False,True,15.0,"90",None])
def test_rejects_invalid_time_limits_except_none(limit):
    if limit is None:
        assert replay(plan(),flat(1),max_holding_minutes=None)["status"]=="OPEN_HYPOTHETICAL"
    else:
        with pytest.raises(ValueError,match="invalid_max_holding_minutes"):
            replay(plan(),flat(3),max_holding_minutes=limit)

def test_unknown_gap_cannot_be_reported_as_time_limit_profit():
    r=replay(plan(),[(T,100,100.5,99.8,100.1),
                     (T+600000,100.1,100.5,99.8,100.2)],
             max_holding_minutes=15)
    assert r["status"]=="UNKNOWN"
    assert "net_pnl_excluding_funding" not in r

def test_invalid_execution_authorization_remains_blocked():
    with pytest.raises(ValueError,match="execution_not_disabled"):
        compare(plan(execution_authorized=True),flat(18))

def test_unbounded_behavior_still_open_when_no_bracket():
    r=replay(plan(),flat(18))
    assert r["status"]=="OPEN_HYPOTHETICAL"
    assert "net_pnl_excluding_funding" not in r

def test_rejects_duplicate_horizons():
    with pytest.raises(ValueError,match="duplicate_horizons"):
        compare(plan(),flat(18),horizons=(15,15))


def test_research_timestamp_offsets_entry_to_next_candle():
    p=plan()
    # The archived signal candle OPEN time is T, so first possible
    # entry candle starts T + 5m. Its own close is T + 10m.
    data=[(T+300000+i*300000,100,100.1,99.9,100)
          for i in range(18)]
    original=dict(p)
    r=compare_research_open_time(p,signal_candle_open_ms=T,candles=data)
    assert p==original
    assert r["research_signal_candle_open_ms"]==T
    assert r["first_possible_entry_candle_open_ms"]==T+300000
    assert r["results"]["90"]["exit_reason"]=="TIME_LIMIT"
    assert r["results"]["90"]["exit_candle_ms"]==T+18*300000


def test_research_timestamp_rejects_signal_candle_entry_data():
    p=plan()
    data=[(T+i*300000,100,100.1,99.9,100) for i in range(18)]
    r=compare_research_open_time(p,signal_candle_open_ms=T,candles=data)
    assert all(x["status"]=="UNKNOWN" for x in r["results"].values())


def test_research_timestamp_mismatch_fails_closed():
    with pytest.raises(ValueError,match="research_plan_timestamp_mismatch"):
        compare_research_open_time(plan(),signal_candle_open_ms=T+300000,candles=flat(18))
