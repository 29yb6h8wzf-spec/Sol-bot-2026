# SignalPilot → FTMO adaptation

Status: **research / offline only**. No FTMO order path exists. Live trading stays disabled under the same release gates as `PRODUCTION_ARCHITECTURE_AND_TASKS.md`.

## Why this is not a config change

| Area | Today (Binance USDT-M) | FTMO |
|---|---|---|
| Execution venue | Binance REST via CCXT | MT4/MT5, cTrader, DXtrade (crypto CFDs) |
| Prices | Binance perpetual mark/last | FTMO liquidity-provider CFD quotes; spread differs |
| Leverage | capped 2x in our code | crypto CFD ~1:3.3 normal, 1:1 Swing |
| Costs | taker fee + funding | commission on crypto volume + spread + swap |
| Hours | 24/7 | crypto CFD sessions can pause; check symbol specs |
| Risk rules | our $150 / $7.50 caps | Max Daily Loss (equity, resets 00:00 CE(S)T) + Max Loss |
| Bot limits | exchange rate limits | forbidden practice: >2,000 server requests/day |

Research results (walk-forward, stage3, seal_candidate_v2_1) were produced on Binance data with Binance costs. **They do not transfer to FTMO without re-running on CFD quotes and CFD costs.**

## Plan

1. **Rules guard** — `ftmo_rules.py` (this PR). Offline, fail-closed; models 2-Step and 1-Step floors, trailing EOD max loss, profit target, Best Day rule, min trading days, Prague trading day, request budget.
2. **Cost model** — add FTMO crypto CFD commission/spread/swap to the walk-forward replay; re-run SOL/XRP/BTC/ETH research and compare with the Binance result.
3. **Data parity** — export FTMO (MT5) history for the same symbols and measure price divergence vs. Binance on the strategy's timeframes (5m/4h).
4. **Challenge simulator** — Monte Carlo of trade sequences through `ftmo_rules` to estimate pass/fail probability and choose per-trade risk (default 0.5% ISC) before paying for a Challenge.
5. **Execution adapter** — MT5 Python bridge (Windows/Wine host) or cTrader Open API, demo/Free Trial only, wired behind `approve_entry` and the existing reconciliation and emergency-flatten guards.
6. **Release gate** — Free Trial run with telemetry before any paid Challenge.

## Defaults in `approve_entry`

- per-trade risk ≤ 0.5% of initial capital
- worst case (all open stops + new stop + costs) must stay ≥ 1% of ISC above the nearest floor
- leverage ≤ 3, margin ≤ equity
- stop new entries at 1,000 requests/day (FTMO flags 2,000)
