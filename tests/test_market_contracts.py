import pytest
from market_contracts import ClosedCandle

BASE = dict(symbol="BTCUSDT", open_ms=300000, timeframe_ms=300000,
            open="100", high="105", low="95", close="102", volume="10",
            now_ms=600000)


def test_closed_candle_valid():
    assert ClosedCandle.from_values(**BASE).close == 102


@pytest.mark.parametrize("patch", [
    {"now_ms": 599999}, {"open_ms": 300001},
    {"high": "99"}, {"low": "103"}, {"close": "NaN"},
    {"volume": "-1"}, {"volume": "Infinity"}, {"open": True},
    {"symbol": "DOGEUSDT"}, {"timeframe_ms": 0},
])
def test_invalid_market_data_fails_closed(patch):
    with pytest.raises(ValueError):
        ClosedCandle.from_values(**(BASE | patch))
