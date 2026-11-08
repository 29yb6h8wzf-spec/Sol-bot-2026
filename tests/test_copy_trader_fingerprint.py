"""Offline fingerprint regression tests: no live account or market dependency."""
import pytest
from tools.copy_trader_fingerprint import analyze


def trade(side="LONG", entry="100", close="102", start="2026-01-01T00:00:00Z", end="2026-01-01T01:00:00Z"):
    return dict(symbol="BTCUSDT", side=side, entryPrice=entry, closePrice=close, openedAt=start, closedAt=end)


def test_fingerprint_counts_direction_and_gross_returns():
    report = analyze([trade(), trade("SHORT", "100", "101", "2026-01-02T00:00:00Z", "2026-01-02T00:30:00Z")])
    assert report["trade_count"] == 2
    assert report["win_rate"] == .5
    assert report["avg_win_notional_pct"] == 2
    assert report["avg_loss_notional_pct"] == -1
    assert report["median_duration_minutes"] == 45
    assert report["overlapping_position_pairs"] == 0


def test_detects_overlapping_positions():
    report = analyze([trade(), trade(start="2026-01-01T00:30:00Z", end="2026-01-01T01:30:00Z")])
    assert report["overlapping_position_pairs"] == 1


def test_milliseconds_timestamp():
    row = trade(start="1767225600000", end="1767229200000")
    assert analyze([row])["median_duration_minutes"] == 60


@pytest.mark.parametrize("bad", [
    trade(side="HOLD"), trade(entry="0"), trade(close="-1"),
    trade(start="2026-01-02T00:00:00Z", end="2026-01-01T00:00:00Z"),
])
def test_rejects_bad_rows(bad):
    with pytest.raises(ValueError):
        analyze([bad])


def test_rejects_empty():
    with pytest.raises(ValueError):
        analyze([])
