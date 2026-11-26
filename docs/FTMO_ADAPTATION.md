# SignalPilot → FTMO (forex only)

Status: **research / offline only**. No FTMO order path exists. Crypto is out of scope: no tested crypto strategy was profitable after costs.

## Open risk, stated up front

EMA_ADX / RSI_BOLL / MACD_VOLUME showed no edge on crypto. Moving the same rules to forex is a hypothesis, not a fix. First gate: **does any candidate show a positive mean per trade on forex holdout data after FTMO costs?** If not, stop before writing execution code.

## Differences that matter

| Area | Binance crypto (old) | FTMO forex |
|---|---|---|
| Venue | Binance REST | MT5 / cTrader / DXtrade |
| Hours | 24/7 | Sun ~22:00 → Fri ~22:00 UTC; holiday closures |
| 4h bars | UTC aligned | MT5 H4 aligned to server time (UTC+2/+3) → rebuild from 5m in UTC |
| Volume | real volume | tick volume only (MACD_VOLUME uses it as a proxy) |
| Costs | taker fee | commission per lot + raw spread (pips) + swap |
| Leverage | 2x cap | up to 1:100 normal, 1:30 Swing |
| Risk rules | own caps | Max Daily Loss (equity, 00:00 CE(S)T) + Max Loss |

## Done

1. `ftmo_rules.py` — 2-Step / 1-Step floors, trailing EOD max loss, profit target, Best Day rule, min days, Prague trading day, request budget, leverage cap by asset class.
2. `signalpilot_walkforward.evaluate` — `spread_rate`, `swap_daily_rate`, `allow_market_closures` (gaps ≤ ~3 days covering a Saturday; mid-week holes still rejected). Defaults keep old results identical.
3. `forex_research.py` — UTC 4h resampling from 5m; pips/commission → fractions (incl. JPY quote conversion).
4. `ftmo_cost_sensitivity.compare` — gross vs FTMO costs across a spread grid.

## Next

1. **Data**: export ≥1 year of 5m history from MT5 (FTMO Free Trial) for the chosen pairs, plus symbol spec (spread, commission, swap long/short).
2. Train-only selection with `allow_market_closures=True` and FTMO costs; report holdout.
3. News-window and session filters.
4. Challenge Monte Carlo through `ftmo_rules` to pick per-trade risk.
5. Only if 1–4 pass: MT5 execution adapter behind `approve_entry`, Free Trial only.
