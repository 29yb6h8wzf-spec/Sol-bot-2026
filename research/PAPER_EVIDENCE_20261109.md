# SignalPilot — SOL/XRP Paper Research Evidence (2026-11-09)

**Verdict: NOT READY for live Binance trading or unattended Paper claims.**

This is a reproducible **historical, in-sample** study using saved public
Binance USDT-M 5m and 4h candles. The scanner is genuine; the simulated
trades are not actual exchange orders, forward trades, or evidence of
profitability. Source: `tests/fixtures/forward_connector_snapshot_20261109_2023utc.json`.

## What was checked

- 141 closed-candle scanner decisions per symbol, using only 4h candles that
  had closed at each 5m decision time.
- Fixed research scanner threshold **85/100**; score is not win probability.
- SOL/XRP USDT-M exchangeInfo snapshot (2026-11-09): SOL step 0.01 and
  tick 0.01; XRP step 0.1 and tick 0.0001; minimum notional 5 USDT.
- Hypothetical next-candle-open fills, 0.5% maximum gap, exchange-quantized
  stop/target, <=2x leverage, $37.50 per-market capital allocation and <=$0.375
  fee/slippage-adjusted estimated stop risk per trade, maximum 30-minute holding, same-bar stop-first policy.
- Skip overlapping positions within the same symbol. This is **not** a
  portfolio-wide margin/daily-loss simulation.
- Funding is **not** included, nor are real order-book fills or connectivity.

## Observed outcomes

| Metric | XRPUSDT | SOLUSDT |
| --- | ---: | ---: |
| Historical scanner decisions | 141 | 141 |
| 85+ candidates | 5 | 2 |
| Simulated closed trades | 4 | 2 |
| Stop exits | 3 | 2 |
| Timed expiry | 1 | 0 |
| Overlapping candidate skipped | 1 | 0 |
| Simulated net PnL (USD) | -0.94945048 | -0.74096622 |

**Total: 7 candidates, 6 simulated closed trades, 5 stop exits, 1
positive timed expiry, 1 skipped overlap; net -1.69041669 USD.**

The earlier $1.50/trade research run was superseded by the stricter
approved per-market 1% ($0.375) cap. All numbers above use the stricter
cap and replace the earlier -$6.80 simulated figure.

The six trades are an extremely small, selected in-sample set. Do not
extrapolate the win rate, expectancy, or any live profit/loss. Stop risk is
an *estimated* model cap, not a guarantee against gap/slippage risk.

## Reproduction

```bash
python -m research.paper_historical_outcomes \
  --input tests/fixtures/forward_connector_snapshot_20261109_2023utc.json
python -m pytest -q tests/test_paper_exchange_rules.py \
  tests/test_paper_historical_outcomes.py \
  tests/test_paper_closed_bar.py
```

On branch `research/paper-signal-adapter-20261109`, GitHub Actions L2
Research CI passed 128 tests on commit `ff787c81ba7df4a3a14fe4f3c089a261c480a6b9`.
Also passed Binance research bridge safety tests and full offline regression.
CI run: https://github.com/29yb6h8wzf-spec/Sol-bot-2026/actions/runs/42703601261

## Blocking items before autonomous Paper or real trading

1. An authorized, compliant, **persistent 5-minute market-data feed** and
   isolated scheduler. The GitHub-hosted runner got Binance **HTTP 451**.
   Do not bypass regional restrictions. The public connector's saved
   snapshot can be imported offline, but it is **not** a running feed.
2. Independent, forward-captured Paper outcomes (not retrospective data).
   Timestamped artifacts alone do not prove capture time without independent
   logs.
3. Out-of-sample validation over substantially more data and trades,
   including historical funding, position overlap, portfolio risk, exchange
   rule refresh, outage recovery, and a locked strategy configuration.
4. A separate explicit user approval before any production merge, deployment,
   or **real Binance orders**. This PR is research-only.

Do not lower score thresholds, increase leverage, or claim readiness to
compensate for negative historical results.
