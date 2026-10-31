"""Offline preflight for a proposed USDT-M futures order.

Produces a deterministic risk assessment only. No credentials, network access,
exchange client, order placement, or live-mode toggle exists here.
Exchange precision, funding, gaps and liquidation are NOT modeled.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


class PreflightRejected(ValueError):
    """A proposed order fails a mandatory risk constraint."""


def _decimal(value, label):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise PreflightRejected(f"{label} must be numeric") from exc
    if not result.is_finite():
        raise PreflightRejected(f"{label} must be finite")
    return result


@dataclass(frozen=True)
class RiskPolicy:
    starting_capital_usdt: str = "150"
    max_leverage: str = "2"
    max_trade_risk_pct: str = "1"
    max_daily_loss_pct: str = "5"
    # Conservative round-trip cost allowance (fees + slippage), not a guarantee.
    round_trip_cost_rate: str = "0.002"


@dataclass(frozen=True)
class OrderProposal:
    symbol: str
    direction: str
    quantity: str
    entry_price: str
    stop_price: str
    leverage: str
    available_margin_usdt: str
    realized_daily_loss_usdt: str
    open_positions: int
    take_profit_price: str


def assess_order(proposal: OrderProposal, policy: RiskPolicy = RiskPolicy()):
    """Return a paper-only plan, or reject before any authenticated API call."""
    if not isinstance(proposal, OrderProposal) or not isinstance(policy, RiskPolicy):
        raise PreflightRejected("invalid preflight inputs")
    if proposal.symbol not in {
        "BTC/USDT:USDT", "ETH/USDT:USDT",
        "SOL/USDT:USDT", "XRP/USDT:USDT",
    }:
        raise PreflightRejected("symbol is not on the approved allowlist")
    if proposal.direction not in ("long", "short"):
        raise PreflightRejected("direction must be long or short")
    if type(proposal.open_positions) is not int or proposal.open_positions != 0:
        raise PreflightRejected("exactly zero open positions required")
    values = {
        name: _decimal(getattr(proposal, name), name)
        for name in (
            "quantity", "entry_price", "stop_price", "take_profit_price",
            "leverage", "available_margin_usdt", "realized_daily_loss_usdt",
        )
    }
    cfg = {
        name: _decimal(getattr(policy, name), name)
        for name in (
            "starting_capital_usdt", "max_leverage", "max_trade_risk_pct",
            "max_daily_loss_pct", "round_trip_cost_rate",
        )
    }
    qty, entry, stop, target = (
        values["quantity"], values["entry_price"],
        values["stop_price"], values["take_profit_price"],
    )
    leverage = values["leverage"]
    capital = cfg["starting_capital_usdt"]
    if any(v <= 0 for v in (qty, entry, stop, target, leverage, capital)):
        raise PreflightRejected("quantity, prices, leverage and capital must be positive")
    if cfg["max_leverage"] <= 0 or not (0 < cfg["max_trade_risk_pct"] <= 100):
        raise PreflightRejected("invalid risk policy")
    if not (0 < cfg["max_daily_loss_pct"] <= 100):
        raise PreflightRejected("invalid daily loss policy")
    if not (0 <= cfg["round_trip_cost_rate"] < 1):
        raise PreflightRejected("invalid modeled cost rate")
    if values["available_margin_usdt"] < 0 or values["realized_daily_loss_usdt"] < 0:
        raise PreflightRejected("margin and daily loss cannot be negative")
    if leverage > cfg["max_leverage"]:
        raise PreflightRejected("leverage exceeds policy")
    if proposal.direction == "long" and not (stop < entry < target):
        raise PreflightRejected("long requires stop below entry and target above entry")
    if proposal.direction == "short" and not (target < entry < stop):
        raise PreflightRejected("short requires target below entry and stop above entry")
    notional = qty * entry
    required_margin = notional / leverage
    if required_margin > values["available_margin_usdt"]:
        raise PreflightRejected("insufficient available margin")
    if notional > capital * cfg["max_leverage"]:
        raise PreflightRejected("notional exceeds account leverage cap")
    max_trade_loss = capital * cfg["max_trade_risk_pct"] / 100
    max_daily_loss = capital * cfg["max_daily_loss_pct"] / 100
    daily_loss = values["realized_daily_loss_usdt"]
    if daily_loss >= max_daily_loss:
        raise PreflightRejected("daily loss circuit breaker reached")
    estimated_loss = qty * abs(entry - stop) + notional * cfg["round_trip_cost_rate"]
    if estimated_loss > max_trade_loss:
        raise PreflightRejected("estimated stop loss exceeds per-trade risk")
    if daily_loss + estimated_loss > max_daily_loss:
        raise PreflightRejected("order would exceed remaining daily loss budget")
    return {
        "mode": "offline_preflight_only",
        "status": "not_submitted",
        "symbol": proposal.symbol,
        "direction": proposal.direction,
        "notional_usdt": str(notional),
        "required_margin_usdt": str(required_margin),
        "estimated_stop_loss_usdt": str(estimated_loss),
        "remaining_daily_budget_usdt": str(max_daily_loss - daily_loss - estimated_loss),
        "assumptions": "modeled costs only; gaps, liquidation, funding and exchange precision not verified",
    }
