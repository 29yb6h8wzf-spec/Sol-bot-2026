import pytest

from research.l2_validation import (
    find_swap_symbol, nearest_snapshot, normalize_book, tracking_complete,
)


def test_normalize_book_types():
    book = {"bids": [[100, 3], [99, 1]], "asks": [[102, 1], [103, 1]]}
    metrics = normalize_book(book)
    assert isinstance(metrics.best_bid, float)
    assert isinstance(metrics.best_ask, float)
    assert metrics.best_bid == 100.0
    assert metrics.best_ask == 102.0
    assert metrics.mid_price == 101.0
    assert metrics.obi == pytest.approx(1 / 3)


def test_invalid_book_rejected():
    with pytest.raises(ValueError):
        normalize_book({"bids": [[102, 1]], "asks": [[100, 1]]})


def test_find_swap_symbol_index():
    markets = [{"base": "SOL", "quote": "USDT", "swap": True,
                "linear": True, "symbol": "SOL/USDT:USDT"}]
    assert find_swap_symbol(markets, "SOL") == "SOL/USDT:USDT"


def test_historical_time_delta_logic():
    rows = [
        {"venue": "okx", "asset": "SOL", "received_ms": 8000},
        {"venue": "okx", "asset": "SOL", "received_ms": 9900},
        {"venue": "okx", "asset": "SOL", "received_ms": 10020},
        {"venue": "bybit", "asset": "SOL", "received_ms": 10000},
    ]
    assert nearest_snapshot(rows, "okx", "SOL", 10000)["received_ms"] == 10020


def test_nearest_tie_prefers_past():
    rows = [{"venue": "okx", "asset": "SOL", "received_ms": t}
            for t in (9900, 10100)]
    assert nearest_snapshot(rows, "okx", "SOL", 10000)["received_ms"] == 9900


def test_tracking_requires_all_horizons():
    signal = {"performance_5m": {"data_status": "valid"},
              "performance_15m": None, "performance_30m": None}
    assert not tracking_complete(signal)
    signal["performance_15m"] = {"data_status": "valid"}
    signal["performance_30m"] = {"data_status": "missing_data"}
    assert tracking_complete(signal)
