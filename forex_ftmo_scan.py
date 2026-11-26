"""Research-only FTMO forex scan: train-only selection, untouched holdout, FTMO costs.

Usage: python forex_ftmo_scan.py SYMBOL PATH_TO_M5_FILE [OUT_JSON]
No orders, no network. Cost inputs are ASSUMPTIONS until checked against the
FTMO MT5 symbol specification (see COSTS below).
"""
import json
import sys
from decimal import Decimal as D

import signalpilot_walkforward as wf
from forex_research import forex_costs, load_m5_tsv, resample_4h
from signalpilot_exit_grid import CANDIDATES

# spread in pips, commission USD per lot round turn. Assumed, not verified.
COSTS = {
    "EURUSD": dict(pip="0.0001", spread_pips="0.2", commission_round_turn_per_lot="5"),
    "GBPUSD": dict(pip="0.0001", spread_pips="0.5", commission_round_turn_per_lot="5"),
    "USDJPY": dict(pip="0.01", spread_pips="0.4", commission_round_turn_per_lot="5", jpy=True),
    "XAUUSD": dict(pip="0.01", spread_pips="20", commission_round_turn_per_lot="5", lot_units="100"),
}
SLIPPAGE = "0.00002"
SWAP_PER_NIGHT = "0.0001"


def _cached_candidates():
    cache = {}
    original = wf.candidates

    def cached(f, h):
        key = (f[-1]["time"], h[-1]["time"], len(h))
        if key not in cache:
            cache[key] = original(f, h)
        return cache[key]
    return cached


def _stats(result, threshold):
    data = result["thresholds"][str(threshold)]
    n = data["trades"]
    return {"trades": n, "wins": data["wins"],
            "mean_net_pct": data["sum_net_return_pct_uncompounded"] / n if n else None,
            "sum_net_pct": data["sum_net_return_pct_uncompounded"]}


def scan(symbol, five, *, min_train_trades=30):
    spec = dict(COSTS[symbol])
    jpy = spec.pop("jpy", False)
    price = sum(r[4] for r in five) / len(five)
    cost = forex_costs(price=price, quote_to_usd=(D(1) / price) if jpy else "1", **spec)
    ftmo = dict(slippage_rate=SLIPPAGE, swap_daily_rate=SWAP_PER_NIGHT, **cost)
    gross = dict(fee_rate="0", slippage_rate="0")
    four = resample_4h(five)
    split = five[len(five) * 7 // 10][0]
    wf.candidates = _cached_candidates()
    rows = []
    for p in CANDIDATES:
        args = dict(thresholds=(p["threshold"],), allowed_strategies=(p["strategy"],),
                    stop_atr=p["stop_atr"], target_atr=p["target_atr"], max_holding_bars=p["hold"],
                    allow_market_closures=True)
        row = {"params": p}
        for label, c in (("gross", gross), ("ftmo", ftmo)):
            row[f"train_{label}"] = _stats(wf.evaluate(five, four, max_exit_ms=split, **c, **args), p["threshold"])
            row[f"holdout_{label}"] = _stats(wf.evaluate(five, four, min_signal_ms=split, **c, **args), p["threshold"])
        rows.append(row)
    qualified = [r for r in rows if r["train_ftmo"]["trades"] >= min_train_trades]
    winner = max(qualified, key=lambda r: r["train_ftmo"]["mean_net_pct"]) if qualified else None
    return {"status": "OFFLINE_RESEARCH_ONLY", "orders_sent": False, "symbol": symbol,
            "bars": len(five), "first_ms": five[0][0], "last_ms": five[-1][0], "split_ms": split,
            "cost_assumptions": {**cost, "slippage_rate": SLIPPAGE, "swap_per_night": SWAP_PER_NIGHT,
                                 **COSTS[symbol], "verified": False},
            "candidates": rows,
            "selected_on_train_only": winner["params"] if winner else None,
            "selected_holdout_ftmo": winner["holdout_ftmo"] if winner else None}


if __name__ == "__main__":
    sym, path = sys.argv[1], sys.argv[2]
    out = scan(sym, load_m5_tsv(path))
    text = json.dumps(out, indent=1, default=str)
    if len(sys.argv) > 3:
        open(sys.argv[3], "w").write(text)
    else:
        print(text)
