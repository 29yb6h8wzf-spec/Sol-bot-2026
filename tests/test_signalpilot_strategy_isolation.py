import pytest
from signalpilot_walkforward import evaluate

def bars(n,step,base):return [[base+i*step,100,101,99,100,1000] for i in range(n)]

def test_filter_does_not_enable_orders():
    x=evaluate(bars(250,300000,14400000*200),bars(250,14400000,0),allowed_strategies=("EMA_ADX",))
    assert x["allowed_strategies"]==["EMA_ADX"]
    assert x["orders_sent"] is False

def test_invalid_filter_rejected():
    with pytest.raises(ValueError,match="invalid_strategy_filter"):
        evaluate(bars(250,300000,14400000*200),bars(250,14400000,0),allowed_strategies=("UNKNOWN",))
