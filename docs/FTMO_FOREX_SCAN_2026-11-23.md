# FTMO forex scan — 2026-11-23

**Result: no candidate has an edge. Do not build execution.**

Data: public M5 (UTC, tick volume) from github.com/TheSnowGuru/Financial-Time-Series-Data-Features, 2021-01 → 2023-09, ~200k bars per pair. Unverified source; short quiet gaps forward-filled (≤4h). XAUUSD skipped (holiday gaps longer than the closure rule allows).
Method: `forex_ftmo_scan.py` — 6 `signalpilot_exit_grid.CANDIDATES`, chronological 70/30 split, selection on train only, holdout untouched.
Costs (assumed, not verified): $5/lot round turn, spread EURUSD 0.2 / GBPUSD 0.5 / USDJPY 0.4 pips, slippage 0.002%/side, swap 0.01%/night. ≈ 0.01% per trade.

Mean net % per trade (holdout):

| Pair | Selected on train | Holdout trades | Gross (no costs) | FTMO costs |
|---|---|---|---|---|
| EURUSD | RSI_BOLL 70 / 3 bars | 466 | +0.0032 | −0.0074 |
| GBPUSD | EMA_ADX 70 / 3 bars | 668 | −0.0032 | −0.0148 |
| USDJPY | RSI_BOLL 70 / 3 bars | 456 | +0.0032 | −0.0090 |

Across all 18 pair×candidate rows the gross mean per trade is within ±0.01% of zero (noise), while costs are ≈0.01%. The only positive FTMO-cost holdout row (EURUSD RSI_BOLL 75/12) has 8 trades — not evidence.

Conclusion: the indicator rules (EMA_ADX, RSI_BOLL, MACD_VOLUME) have no measurable edge on forex 5m either; it is the strategies, not the asset class. Next work must be a different hypothesis (e.g. longer holding / higher timeframe so costs are a smaller share of the move, or session/structure-based entries), tested through the same harness before anything else.
