"""Paper crossover must fail closed on invalid market closes."""
from decimal import Decimal
import pytest
from futures_engine.core import crossover_signal


def bars():
    return [[i * 900000, 100, 101, 99, 100, 10] for i in range(202)]


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity", "0", "-1"])
def test_crossover_rejects_bad_close(bad):
    candles = bars()
    candles[42][4] = Decimal(bad)
    with pytest.raises(ValueError, match="invalid candle prices"):
        crossover_signal(candles)


def test_crossover_finite_flat_series_is_no_signal():
    assert crossover_signal(bars()) is None
