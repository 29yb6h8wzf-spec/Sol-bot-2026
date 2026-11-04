import pytest
from futures_engine.closed_candle_validation import validate_rows, CandleValidationError


def rows(count=202, start=0, interval=300000):
    return [[start+i*interval, 100, 105, 95, 102, 10] for i in range(count)]


def test_valid_closed_rows():
    data=rows()
    assert len(validate_rows("BTCUSDT",300000,data,202*300000))==202


def test_open_candle_dropped():
    data=rows(203)
    assert len(validate_rows("BTCUSDT",300000,data,202*300000))==202


@pytest.mark.parametrize("idx,val",[(2,float("nan")),(4,float("inf")),(5,-1)])
def test_invalid_numbers_rejected(idx,val):
    data=rows()
    data[100][idx]=val
    with pytest.raises(CandleValidationError):
        validate_rows("BTCUSDT",300000,data,202*300000)


def test_duplicate_rejected():
    data=rows()
    data[100][0]=data[99][0]
    with pytest.raises(CandleValidationError):
        validate_rows("BTCUSDT",300000,data,202*300000)
