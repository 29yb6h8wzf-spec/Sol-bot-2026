# US100 triple strategy for the FTMO challenge (2026-11-23)

EA: `mt5/US100TripleEA.mq5`, preset `mt5/US100TripleEA.set` (2.0x notional per module).
Launcher `mt5/start_trading.py` now starts this EA on `US100.cash` M5 and only kills the trading terminal.

## How we got here
| Search | Scope | Result |
|---|---|---|
| Oil breakout (GPT) | USOIL M15, 155 trades 2026 / 180 trades 2024 | +0.03%/trade (t 0.3) then -0.21%/trade (t -2.3) out of sample: rejected |
| EIA Wednesday reaction | 70 Wednesdays | -0.14%/trade (t -0.9): rejected |
| Calendar scan | 31 FTMO-tradable assets, TOM + day-of-week, Holm | only cocoa Monday passed, flipped sign 2016+: rejected; TOM positive across equity indices |
| 99 strategies x 31 assets | daily, costs + swap, pick on <=2015, test 2016+ | top-25 by discovery: mean 2016+ Sharpe 0.01 (luck). Survivor: US100 RSI(2)<10 dip-buy, t 4.2 -> 4.5 |
| Commodities/FX best-per-asset + monthly seasonality | 20 assets | mean ~0; natgas seasonal +0.52 Sharpe on Yahoo, but FTMO NATGAS.cash swap ~-17 pts/lot/night (~190%/yr long): rejected |
| Trend-following portfolio (TSMOM 60/120/250) | 31 assets, vol-targeted, CFD costs | negative in all periods: rejected |
| ORB (Zarattini & Aziz) | literature | independent CFD replication: net ~0 on NQ/SPX/Dow/DAX/FTSE: not tested further |
| "Beat the Market" intraday momentum | FTMO M5 2021-10..2026-11 | US500 net +0.5%/yr (post-publication -4.6%); US100 net +7.3%/yr, Sharpe 0.80, t 1.8, positive every year but decaying |

## Combined (US100, FTMO data 2021-10..2026-11, 1x per module, net)
| | ann | Sharpe |
|---|---|---|
| DIP (RSI2) | +11.2% | 0.95 |
| BTM (intraday momentum, long/short) | +7.3% | 0.80 |
| TOM | +1.1% | 0.13 |
| All three | +19.6% | 1.06 |
Correlations 0.02-0.14.

Phase 1 (10%) bootstrap, 5-day blocks, daily-close granularity (intraday drawdowns not modelled):
| size | 63 days pass/fail | 126 days | 252 days |
|---|---|---|---|
| 1.0x | 33% / 10% | 59% / 18% | 75% / 21% |
| 1.5x | 49% / 27% | 61% / 35% | 65% / 35% |
| 2.0x | 51% / 41% | 55% / 44% | 55% / 45% |
| 5.0x (63 days) | 41% / 59% | | |
User chose 2.0x to target ~3 months.

## MT5 tester check (US100.cash M5, 1-min OHLC, 2025-01-01..2026-11-20, $10k, 2.0x)
Net +$9,780, PF 1.51, 439 trades (TOM 20, DIP 30, BTM 389), equity max DD 17.3% (from a peak),
17 daily-stop events, no total-stop event, no failed orders.

## Known limits
- Only ~5 years of FTMO intraday data; BTM edge is decaying; TOM on US100 weak in this window.
- Simulation uses daily closes; FTMO daily loss is intraday equity, so real fail rates are higher.
- Daily stop at 4% of ISC vs FTMO 5%; total stop 8% vs FTMO 10%.
- Half-day / holiday list hard-coded through 2027.
