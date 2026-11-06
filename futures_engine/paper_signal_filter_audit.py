"""Explain why an offline 15-minute Paper EMA50/200 + RSI14 signal is absent.

This module is *pure*: it cannot fetch candles, write ledgers, or trade.
The caller must pass already-closed bars. It uses the exact same EMA/RSI
formulas and strict threshold comparisons as futures_engine.core.
"""
from decimal import Decimal, InvalidOperation

from .core import ema, rsi


def explain_paper_signal(closed_bars):
    """Inspect a single Paper scan without changing its trading decision.

    A return value is diagnostic data, NOT an independently validated signal
    or any order instruction. No source authentication is implied.
    """
    if not isinstance(closed_bars, (list, tuple)) or len(closed_bars) < 202:
        raise ValueError("insufficient_paper_signal_bars")
    prices = []
    for row in closed_bars:
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            raise ValueError("invalid_paper_signal_bar")
        try:
            value = Decimal(str(row[4]))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("invalid_paper_close") from exc
        if not value.is_finite() or value <= 0:
            raise ValueError("invalid_paper_close")
        prices.append(value)

    fast_before, slow_before = ema(prices[:-1], 50), ema(prices[:-1], 200)
    fast_now, slow_now = ema(prices, 50), ema(prices, 200)
    momentum = rsi(prices)

    long_cross = fast_before <= slow_before and fast_now > slow_now
    short_cross = fast_before >= slow_before and fast_now < slow_now
    if long_cross and momentum < 55:
        condition, candidate = "LONG_PASSED", "long"
    elif short_cross and momentum > 45:
        condition, candidate = "SHORT_PASSED", "short"
    elif long_cross:
        condition, candidate = "LONG_CROSS_RSI_NOT_BELOW_55", None
    elif short_cross:
        condition, candidate = "SHORT_CROSS_RSI_NOT_ABOVE_45", None
    else:
        condition, candidate = "NO_EMA_CROSS", None
    return {
        "status": "OFFLINE_SIGNAL_DIAGNOSTIC_ONLY",
        "condition": condition,
        "candidate": candidate,
        "ema50_before": str(fast_before),
        "ema200_before": str(slow_before),
        "ema50_now": str(fast_now),
        "ema200_now": str(slow_now),
        "rsi14": str(momentum),
        "rsi_long_requires_below": "55",
        "rsi_short_requires_above": "45",
        "closed_bars_supplied": len(prices),
        "market_source_authenticated": False,
        "orders_sent": False,
        "execution_authorized": False,
    }


def count_paper_filter_reasons(closed_bar_snapshots):
    """Summarize archived, supplied snapshots, not live market performance."""
    if not isinstance(closed_bar_snapshots, (list, tuple)):
        raise ValueError("invalid_snapshot_sequence")
    counts = {}
    for snapshot in closed_bar_snapshots:
        reason = explain_paper_signal(snapshot)["condition"]
        counts[reason] = counts.get(reason, 0) + 1
    return {
        "status": "OFFLINE_SIGNAL_DIAGNOSTIC_COUNTS_ONLY",
        "snapshots_checked": len(closed_bar_snapshots),
        "reason_counts": counts,
        "market_source_authenticated": False,
        "orders_sent": False,
        "execution_authorized": False,
    }
