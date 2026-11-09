"""Offline-only deterministic paper execution. No exchange client or database access."""
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Literal

D = Decimal
Side = Literal["LONG", "SHORT"]


@dataclass(frozen=True)
class PaperTrade:
    signal_uid: str
    side: Side
    quantity: Decimal
    entry: Decimal
    stop: Decimal
    target: Decimal
    opened_at: int
    expires_at: int
    status: str = "OPEN"
    exit_price: Decimal | None = None
    gross_pnl: Decimal | None = None
    net_pnl: Decimal | None = None


class PaperOrderManager:
    """In-memory paper-only manager; state must be persisted by a future adapter."""

    def __init__(self, taker_fee="0.0005", slippage="0.0002"):
        self.fee = D(taker_fee)
        self.slippage = D(slippage)
        if not (D(0) <= self.fee < D(1) and D(0) <= self.slippage < D(1)):
            raise ValueError("invalid friction parameters")
        self.trades: dict[str, PaperTrade] = {}

    def open(self, uid: str, side: Side, quantity, mid, stop, target,
             timestamp: int, holding_seconds: int = 1800) -> PaperTrade:
        if uid in self.trades:
            return self.trades[uid]
        q, m, sl, tp = map(D, (quantity, mid, stop, target))
        if not uid or side not in ("LONG", "SHORT") or q <= 0 or m <= 0 or holding_seconds <= 0:
            raise ValueError("invalid paper order")
        if side == "LONG" and not (0 < sl < m < tp):
            raise ValueError("invalid LONG protection")
        if side == "SHORT" and not (0 < tp < m < sl):
            raise ValueError("invalid SHORT protection")
        entry = m * (1 + self.slippage if side == "LONG" else 1 - self.slippage)
        trade = PaperTrade(uid, side, q, entry, sl, tp, timestamp, timestamp + holding_seconds)
        self.trades[uid] = trade
        return trade

    def update(self, uid: str, high, low, close, timestamp: int) -> PaperTrade:
        trade = self.trades[uid]
        if trade.status != "OPEN" or timestamp < trade.opened_at:
            return trade
        hi, lo, last = map(D, (high, low, close))
        if not (0 < lo <= last <= hi):
            raise ValueError("invalid market bar")
        if trade.side == "LONG":
            stop_hit, target_hit = lo <= trade.stop, hi >= trade.target
        else:
            stop_hit, target_hit = hi >= trade.stop, lo <= trade.target
        # Ambiguous same-bar execution is conservatively marked as a stop.
        if stop_hit:
            status, raw_exit = "EXECUTED_SL", trade.stop
        elif target_hit:
            status, raw_exit = "EXECUTED_TP", trade.target
        elif timestamp >= trade.expires_at:
            status, raw_exit = "EXPIRED", last
        else:
            return trade
        exit_price = raw_exit * (1 - self.slippage if trade.side == "LONG" else 1 + self.slippage)
        direction = D(1) if trade.side == "LONG" else D(-1)
        gross = direction * (exit_price - trade.entry) * trade.quantity
        fees = self.fee * trade.quantity * (trade.entry + exit_price)
        finished = replace(trade, status=status, exit_price=exit_price,
                           gross_pnl=gross, net_pnl=gross - fees)
        self.trades[uid] = finished
        return finished
