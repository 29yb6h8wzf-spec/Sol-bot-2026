"""Fail-closed closed-candle adapter for offline paper position updates."""
from dataclasses import dataclass
from decimal import Decimal

from research.paper_order_store import DurablePaperOrders


@dataclass(frozen=True)
class ClosedBar:
    open_ms: int
    close_ms: int
    high: Decimal
    low: Decimal
    close: Decimal
    confirmed_closed: bool


def apply_closed_bar(store: DurablePaperOrders, uid: str, bar: ClosedBar, observed_at_ms: int):
    """Never evaluate an unclosed, future, malformed or pre-entry candle."""
    trade = store.get(uid)
    if trade is None:
        raise KeyError(uid)
    if not bar.confirmed_closed:
        raise ValueError("unconfirmed candle")
    if not (0 <= bar.open_ms < bar.close_ms <= observed_at_ms):
        raise ValueError("future or invalid candle timestamps")
    if bar.open_ms < trade.opened_at * 1000:
        raise ValueError("candle overlaps pre-entry period")
    if not (Decimal(0) < bar.low <= bar.close <= bar.high):
        raise ValueError("invalid OHLC candle")
    return store.update(uid, bar.high, bar.low, bar.close, (bar.close_ms + 1) // 1000)
