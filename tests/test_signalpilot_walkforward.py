import pytest
from signalpilot_walkforward import evaluate

def bars(n,step,base):return [[base+i*step,100,101,99,100,1000] for i in range(n)]

def test_research_only():
    result=evaluate(bars(250,300000,14400000*200),bars(250,14400000,0))
    assert result["orders_sent"] is False and result["funding_included"] is False
    assert all(v["trades"]==0 for v in result["thresholds"].values())

def test_gap_rejected():
    f=bars(250,300000,14400000*200);f[30][0]+=300000
    with pytest.raises(ValueError,match="gapped_candles"):evaluate(f,bars(250,14400000,0))

def test_invalid_cost_rejected():
    with pytest.raises(ValueError,match="invalid_assumptions"):evaluate(bars(250,300000,14400000*200),bars(250,14400000,0),fee_rate="-0.1")
