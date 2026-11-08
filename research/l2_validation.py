"""Pure, offline L2 validation helpers. No exchange or database access."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any


@dataclass(frozen=True)
class BookMetrics:
    best_bid: float
    best_ask: float
    mid_price: float
    obi: float


def normalize_book(book: dict[str, Any], contract_size: float = 1.0) -> BookMetrics:
    bids = [(float(p), float(q) * contract_size) for p, q, *_ in book.get("bids", [])[:20]]
    asks = [(float(p), float(q) * contract_size) for p, q, *_ in book.get("asks", [])[:20]]
    if not bids or not asks or contract_size <= 0:
        raise ValueError("missing or invalid order book")
    if any(not isfinite(p) or not isfinite(q) or p <= 0 or q <= 0 for p, q in bids + asks):
        raise ValueError("invalid price or quantity")
    best_bid, best_ask = bids[0][0], asks[0][0]
    if best_bid >= best_ask:
        raise ValueError("crossed or locked book")
    bid_qty = sum(q for _, q in bids[:5])
    ask_qty = sum(q for _, q in asks[:5])
    return BookMetrics(best_bid, best_ask, (best_bid + best_ask) / 2,
                       (bid_qty - ask_qty) / (bid_qty + ask_qty))


def find_swap_symbol(markets: list[dict[str, Any]], asset: str) -> str:
    matches = [m for m in markets if m.get("base") == asset and m.get("quote") == "USDT"
               and m.get("swap") and m.get("linear") and m.get("active") is not False]
    if not matches:
        raise LookupError(f"No active linear USDT swap for {asset}")
    return str(matches[0]["symbol"])


def nearest_snapshot(snapshots: list[dict[str, Any]], venue: str, asset: str,
                     target_ms: int, tolerance_ms: int = 6000) -> dict[str, Any] | None:
    eligible = [s for s in snapshots if s["venue"] == venue and s["asset"] == asset
                and abs(s["received_ms"] - target_ms) <= tolerance_ms]
    return min(eligible, key=lambda s: (abs(s["received_ms"] - target_ms),
                                        s["received_ms"])) if eligible else None


def tracking_complete(signal: dict[str, Any]) -> bool:
    return all(signal.get(f"performance_{m}m") is not None for m in (5, 15, 30))


RESEARCH_WINDOW_SECONDS = 72 * 3600
SNAPSHOT_TTL_SECONDS = 96 * 3600


def snapshot_expiry(received_ms: int, ttl_seconds: int = SNAPSHOT_TTL_SECONDS) -> datetime:
    """Return a BSON-compatible UTC expiry timestamp for raw snapshots."""
    if ttl_seconds <= RESEARCH_WINDOW_SECONDS:
        raise ValueError("snapshot TTL must exceed the research window")
    return datetime.fromtimestamp(received_ms / 1000, tz=timezone.utc) + timedelta(
        seconds=ttl_seconds
    )


def asof_snapshot(snapshots: list[dict[str, Any]], venue: str, asset: str,
                  target_ms: int, tolerance_ms: int = 6000) -> dict[str, Any] | None:
    """Select only data observed at or before a decision timestamp."""
    eligible = [s for s in snapshots if s["venue"] == venue and s["asset"] == asset
                and 0 <= target_ms - s["received_ms"] <= tolerance_ms]
    return max(eligible, key=lambda s: s["received_ms"]) if eligible else None
