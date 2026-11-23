# S&P 500 turn-of-month — the first edge that survives — 2026-11-23

`tom_research.py`, daily S&P 500 closes 1950–2025 (github.com/SteelCerberus/us-market-data, Yahoo-based, unverified).
Rule: long at close of the last trading day of the month, exit at close of the 3rd trading day.

**Edge:** 911 trades 1950–2025, mean +0.383 % per 3-day hold vs +0.109 % for any 3-day hold (t = +4.7). Positive excess in **every decade** 1950s–2020s (+0.14 % to +0.55 %). Economic reason: month-start flows (salaries, pensions, fund rebalancing).

**After assumed CFD costs (1990–2025):** 431 trades (12/yr), +0.245 %/trade, win 59 %, worst −8.2 % → ≈ +3 %/yr at 1× notional.

**FTMO 2-Step simulation** (start every month 1990–2023, daily closes only):

| Notional | Pass | Fail daily | Fail total | Still running | Median months |
|---|---|---|---|---|---|
| 1× (24 m) | 42 % | 2 % | 9 % | 46 % | 12 |
| 1× (60 m) | 63 % | 5 % | 13 % | 19 % | 16 |
| 1.5× | 48 % | 19 % | 10 % | 23 % | 8 |
| 2× | 47 % | 41 % | 3 % | 9 % | 5 |
| 3× | 44 % | 50 % | 6 % | 0 % | 2 |

Real but small: more leverage only trades waiting time for daily-loss failures. SMA200 filter did not help.
