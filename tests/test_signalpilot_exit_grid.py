import pytest
from signalpilot_exit_grid import run

def bars(n,step,base):return [[base+i*step,100,101,99,100,1000] for i in range(n)]

def test_no_winner_on_flat_market():
    result=run(bars(1000,300000,14400000*200),bars(250,14400000,0))
    assert result["orders_sent"] is False
    assert result["selected_train_only"] is None
    assert result["holdout"] is None

def test_invalid_strategy_rejected():
    with pytest.raises(ValueError,match="invalid_strategy"):
        run(bars(1000,300000,14400000*200),bars(250,14400000,0),candidates=({"strategy":"UNKNOWN"},))
