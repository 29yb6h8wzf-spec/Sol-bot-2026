"""Locked, research-only SignalPilot V3 hypothesis contract.

No orders, credentials, exchange calls, or automatic promotion.
User-requested 5x / 2% / 8% are NOT authorized risk settings.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class V3ResearchSpec:
    schema: str = "signalpilot.v3.research.1"
    capital_usd: float = 150.0
    max_leverage: float = 2.0
    max_risk_fraction_of_market_allocation: float = 0.01
    max_daily_loss_fraction: float = 0.05
    max_concurrent_positions: int = 3
    target_rr: float = 2.0
    desired_daily_trades_min: int = 10
    desired_daily_trades_max: int = 25
    minimum_research_trades: int = 1000
    research_months: int = 24
    train_months: int = 18
    locked_oos_months: int = 6
    strategies: tuple[str, ...] = ("trend_pullback", "volatility_breakout", "liquidity_reversal")
    execution_authorized: bool = False
    research_only: bool = True

    def validate(self) -> None:
        if self.max_leverage > 2 or self.max_risk_fraction_of_market_allocation > .01:
            raise ValueError("risk_limits_exceeded")
        if self.max_daily_loss_fraction > .05 or self.max_concurrent_positions > 3:
            raise ValueError("portfolio_limits_exceeded")
        if self.execution_authorized or not self.research_only:
            raise ValueError("research_only_required")
        if self.train_months + self.locked_oos_months != self.research_months:
            raise ValueError("invalid_chronological_split")
        if self.minimum_research_trades < 1000:
            raise ValueError("insufficient_research_sample")

SPEC = V3ResearchSpec()
SPEC.validate()
