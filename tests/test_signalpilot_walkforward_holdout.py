import pytest
from signalpilot_walkforward import evaluate

def bars(n,step,base):return [[base+i*step,100,101,99,100,1000] for i in range(n)]

def test_configurable_exits_remain_offline():
    f=bars(250,300000,14400000*200);h=bars(250,14400000,0)
    result=evaluate(f,h,stop_atr="1.5",target_atr="2",min_signal_ms=f[230][0],max_exit_ms=f[-1][0])
    assert result["orders_sent"] is False
    assert result["stop_atr"]=="1.5" and result["target_atr"]=="2"
    assert all(v["trades"]==0 for v in result["thresholds"].values())

def test_invalid_exits_and_boundary_fail_closed():
    f=bars(250,300000,14400000*200);h=bars(250,14400000,0)
    with pytest.raises(ValueError,match="invalid_assumptions"):evaluate(f,h,stop_atr="0")
    with pytest.raises(ValueError,match="invalid_max_exit_ms"):evaluate(f,h,max_exit_ms=1)
