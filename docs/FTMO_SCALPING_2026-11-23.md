# EURUSD scalping on real M1 — 2026-11-23

Data: HistData.com EURUSD M1 BID, full year 2025 (372k bars, user-supplied). Costs per round trip: FTMO raw spread 0.09 pip + $5/lot commission (0.5 pip) + 0.1 pip slippage per market fill. `scalp_research.py`.
(An earlier upload "EURUSD_M1_2025_2026.csv" was rejected as synthetic: 16-decimal prices, trading on Jan 1/Dec 25, flat hourly volatility, kurtosis ≈ 0.)

| Hypothesis | Trades/day | Gross pips/trade | Net pips/trade | t |
|---|---|---|---|---|
| Fade 5-min spike, k=2 (≈50/day) | 52.8 | +0.03 | −0.70 | −21.6 |
| Follow 5-min spike, k=2 (≈50/day) | 53.7 | −0.21 | −0.95 | −28.1 |
| Fade k=4 | 6.8 | +0.24 | −0.50 | −3.3 |
| London 30-min ORB, 2R | 1.0 | +1.98 | +1.22 | +1.2 |
| NY 30-min ORB, 1R | 1.0 | +1.62 | +0.87 | +0.9 |

50 trades/day: gross ≈ 0, costs ≈ 0.7 pip → about −37 pips/day (−$370/day at 1 lot).
ORB check on independent data (M5 2021–2023): EURUSD London 2R −0.73 pip, NY 1R −0.45 pip; GBPUSD ≈ 0 or negative. The 2025 ORB result does not replicate → noise.
