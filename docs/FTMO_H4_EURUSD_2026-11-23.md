# EURUSD H4 scan — 2026-11-23

Data: public H4 (UTC) 2007-09 → 2023-09. Train 2007–2018, holdout 2019–2023-09. Real FTMO EURUSD swap (−9.25 / +0.3 points) and $5/lot commission. `h4_eurusd_scan.py` (18 configs from `h1_research.GRID`, London family dropped on H4).

Only candidate positive on both train and holdout: **RSI(2) mean reversion, lo=5, EMA200 filter, 3 ATR stop, exit close > EMA5, max 24 bars.**

| | Trades | Mean R | Std R | t | Win |
|---|---|---|---|---|---|
| Train | 418 | +0.038 | 0.45 | 1.72 | 67% |
| Holdout | 151 | +0.059 | 0.46 | 1.57 | 65% |

Caveats: best of 18 configs (multiple testing); does not generalise (holdout GBPUSD −0.021R, USDJPY −0.009R); t < 2 in each period.
Size of the edge if real: ~32 trades/year × 0.059R ≈ **1.9R per year** → 1.9%/yr at 1% risk, ~5.7%/yr at 3% risk. Too slow for a 10% Challenge target.

Everything else (Donchian, EMA pullback, RSI2 lo=10) is negative on EURUSD holdout after costs.

## Update: all 17 pairs with real FTMO spreads/swaps (user-supplied spec sheet)

RSI(2) lo=5 on H4, pooled: train 6,806 trades −0.001R (t −0.11), holdout 2,831 trades −0.005R (t −0.54). EURUSD's +0.06R is one of 17 pair results scattered around zero → **noise, not an edge.** Strategy rejected.
