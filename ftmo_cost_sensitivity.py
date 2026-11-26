"""Research-only: does a SignalPilot candidate survive FTMO forex costs?

Runs the same walk-forward candidate with zero costs (gross edge) and with
FTMO commission + spread + swap across a spread grid (in pips), and reports the
widest tested spread that still leaves a positive mean per trade.
No orders, no network. Input: closed 5m forex candles; 4h is rebuilt in UTC.
"""
from forex_research import forex_costs, resample_4h
from signalpilot_walkforward import evaluate

SPREAD_GRID_PIPS = ("0.1", "0.3", "0.5", "1.0")


def _stats(result, threshold):
    data = result["thresholds"][str(threshold)]
    n = data["trades"]
    mean = data["sum_net_return_pct_uncompounded"] / n if n else None
    return {"trades": n, "wins": data["wins"], "mean_net_pct": mean,
            "sum_net_pct_uncompounded": data["sum_net_return_pct_uncompounded"]}


def compare(five, candidate, *, price, pip, commission_round_turn_per_lot, swap_daily_rate,
            quote_to_usd="1", slippage_rate="0.00002", spreads_pips=SPREAD_GRID_PIPS, **window):
    """candidate: one entry shaped like signalpilot_exit_grid.CANDIDATES.
    commission and swap are required so nobody runs with silent zero costs."""
    if candidate.get("strategy") not in ("EMA_ADX", "RSI_BOLL", "MACD_VOLUME"):
        raise ValueError("invalid_strategy")
    if not spreads_pips:
        raise ValueError("invalid_spread_grid")
    four = resample_4h(five)
    t = candidate["threshold"]
    args = dict(thresholds=(t,), allowed_strategies=(candidate["strategy"],),
                stop_atr=candidate["stop_atr"], target_atr=candidate["target_atr"],
                max_holding_bars=candidate["hold"], allow_market_closures=True, **window)
    gross = _stats(evaluate(five, four, fee_rate="0", slippage_rate="0", **args), t)
    ftmo = []
    for pips in sorted(spreads_pips, key=float):
        cost = forex_costs(price=price, spread_pips=pips, pip=pip, quote_to_usd=quote_to_usd,
                           commission_round_turn_per_lot=commission_round_turn_per_lot)
        res = evaluate(five, four, slippage_rate=slippage_rate, swap_daily_rate=swap_daily_rate, **cost, **args)
        ftmo.append({"spread_pips": str(pips), **cost, **_stats(res, t)})
    survivors = [x for x in ftmo if x["mean_net_pct"] is not None and x["mean_net_pct"] > 0]
    return {"status": "OFFLINE_RESEARCH_ONLY", "orders_sent": False, "candidate": candidate,
            "gross_no_costs": gross, "ftmo": ftmo,
            "max_tested_spread_pips_with_positive_mean": survivors[-1]["spread_pips"] if survivors else None,
            "ftmo_assumptions_verified": False}
