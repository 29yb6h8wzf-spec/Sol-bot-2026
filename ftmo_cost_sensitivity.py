"""Research-only: does a SignalPilot candidate survive FTMO crypto-CFD costs?

Runs the same walk-forward candidate under the Binance cost profile and under
FTMO CFD costs across a spread grid, and reports the break-even spread.
No orders, no network. Input candles must be preloaded closed 5m/4h rows.

FTMO numbers are assumptions to be replaced with the MT5/cTrader symbol
specification of the account actually used (spread is quoted per symbol and
changes with liquidity; swap is per symbol and per direction).
"""
from decimal import Decimal as D
from signalpilot_walkforward import evaluate

BINANCE = {"fee_rate": "0.0006", "slippage_rate": "0.0005", "spread_rate": "0", "swap_daily_rate": "0"}
# Commission 0.065% of crypto volume per side (published FTMO cTrader conditions).
FTMO_CRYPTO_BASE = {"fee_rate": "0.00065", "slippage_rate": "0.0005"}
SPREAD_GRID = ("0.0005", "0.001", "0.002", "0.003")


def _stats(result, threshold):
    data = result["thresholds"][str(threshold)]
    n = data["trades"]
    mean = data["sum_net_return_pct_uncompounded"] / n if n else None
    return {"trades": n, "wins": data["wins"], "mean_net_pct": mean,
            "sum_net_pct_uncompounded": data["sum_net_return_pct_uncompounded"]}


def compare(five, four, candidate, *, swap_daily_rate, spreads=SPREAD_GRID, **window):
    """candidate: one entry shaped like signalpilot_exit_grid.CANDIDATES.
    swap_daily_rate is required (fraction of notional per rollover) so nobody
    forgets it; pass "0" only after checking the symbol spec."""
    if candidate.get("strategy") not in ("EMA_ADX", "RSI_BOLL", "MACD_VOLUME"):
        raise ValueError("invalid_strategy")
    if not spreads:
        raise ValueError("invalid_spread_grid")
    t = candidate["threshold"]
    args = dict(thresholds=(t,), allowed_strategies=(candidate["strategy"],),
                stop_atr=candidate["stop_atr"], target_atr=candidate["target_atr"],
                max_holding_bars=candidate["hold"], **window)
    binance = _stats(evaluate(five, four, **BINANCE, **args), t)
    ftmo = []
    for spread in sorted(spreads, key=D):
        cost = dict(FTMO_CRYPTO_BASE, spread_rate=spread, swap_daily_rate=swap_daily_rate)
        ftmo.append({"spread_rate": str(spread), **_stats(evaluate(five, four, **cost, **args), t)})
    survivors = [x for x in ftmo if x["mean_net_pct"] is not None and x["mean_net_pct"] > 0]
    return {"status": "OFFLINE_RESEARCH_ONLY", "orders_sent": False,
            "candidate": candidate, "binance": binance, "ftmo": ftmo,
            "max_tested_spread_with_positive_mean": survivors[-1]["spread_rate"] if survivors else None,
            "ftmo_assumptions_verified": False}
