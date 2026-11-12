"""Offline conservative replay tests; synthetic prices are not evidence."""
from dataclasses import replace
import pytest
from signals_v2.contracts import Candle, DataRejected
from signals_v2.hybrid import Hypothesis
from signals_v2.replay import replay

BASE = 1_800_000_000_000


def proposal(direction="LONG"):
    return Hypothesis("signals.v2.research.1", "SOLUSDT", direction,
                      "breakout_expansion", "BREAKOUT_TRANSITION",
                      BASE, 100, 98 if direction == "LONG" else 102,
                      104 if direction == "LONG" else 96,
                      BASE + 600_000)


def bar(i=0, o=100, h=105, l=97, c=101):
    return Candle(BASE + i * 300_000, o, h, l, c, 10,
                  BASE + (i+1) * 300_000)


def test_same_bar_target_and_stop_is_stop_first_long():
    result = replay(proposal(), (bar(),))
    assert result.exit_reason == "STOP"
    assert result.net_r < 0
    assert result.research_only


def test_same_bar_target_and_stop_is_stop_first_short():
    result = replay(proposal("SHORT"), (bar(),))
    assert result.exit_reason == "STOP"
    assert result.net_r < 0


def test_target_only_and_fees_reduce_return():
    candle = bar(h=105, l=99)
    free = replay(proposal(), (candle,), fee_rate_per_side=0,
                  slippage_rate_per_side=0)
    paid = replay(proposal(), (candle,))
    assert free.exit_reason == "TARGET"
    assert paid.exit_reason == "TARGET"
    assert paid.net_r < free.net_r


def test_timeout_marks_to_market():
    result = replay(proposal(), (bar(h=101, l=99, c=100.5),))
    assert result.exit_reason == "TIMEOUT"
    assert result.bars_held == 1


def test_funding_direction_sign():
    candle = bar(h=101, l=99, c=100)
    long_no = replay(proposal(), (candle,), funding_rate_total=0)
    long_paid = replay(proposal(), (candle,), funding_rate_total=0.0001)
    assert long_paid.net_r < long_no.net_r
    short_no = replay(proposal("SHORT"), (candle,), funding_rate_total=0)
    short_received = replay(proposal("SHORT"), (candle,), funding_rate_total=0.0001)
    assert short_received.net_r > short_no.net_r


def test_rejects_nonresearch_and_expired_entry():
    with pytest.raises(DataRejected, match="not_research"):
        replay(replace(proposal(), execution_authorized=True), (bar(),))
    with pytest.raises(DataRejected, match="expired_entry"):
        replay(proposal(), (bar(3),))


def test_rejects_future_window_gap():
    with pytest.raises(DataRejected, match="missing_future_bar"):
        replay(proposal(), (bar(0, h=101, l=99), bar(2)), max_bars=3)
