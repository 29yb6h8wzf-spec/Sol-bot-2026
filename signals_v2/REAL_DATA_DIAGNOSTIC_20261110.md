# Signals V2 public-market replay diagnostic — 2026-11-10

**Status: NOT_READY.** This is a short, recent, overlapping public-data
**smoke diagnostic**, not a registered backtest, OOS experiment, A/B comparison,
proof of profitability, or evidence of future results.

## Reproduction

Run `PYTHONPATH=. python -m signals_v2.public_smoke` on a research-only
environment with read-only public network access. Source:
`https://fapi.binance.com/fapi/v1/klines` (Binance USDT-M public 1m/5m klines).
The runner fetches 1,000 5m and 1,000 1m candles per symbol, only evaluates
the overlapping portion with 80 5m warmup bars and 10 confirming 1m bars,
and requires 48 subsequent 5m candles for a complete four-hour horizon.
It hashes raw fetched responses, and uses a synthetic historical
availability-at-close assumption. No private endpoints, API keys or orders.

## Observed result of isolated run

| Symbol | Eligible decisions | Abstentions | Hypotheses replayed | STOP | TARGET | TIMEOUT | Sum net R |
|---|---:|---:|---:|---:|---:|---:|---:|
| SOLUSDT | 150 | 128 | 22 | 13 | 5 | 4 | -8.6823 |
| XRPUSDT | 150 | 131 | 19 | 15 | 1 | 3 | -15.7739 |

Data snapshot SHA-256, SOL:
`a7248c4d31567e9f53c5b5d4b8bfb7356c6d7fdfdc2b0353eb18655ce97b3f89`

Data snapshot SHA-256, XRP:
`8519f69e94843d5dbcecfed43f2b2935ede8c8a1963bb3b82137826dfa66f8f4`

**Important:** 41 replayed proposals are not necessarily independent,
nonoverlapping economic trades; overlapping positions were not suppressed.
The sums of R must not be interpreted as a feasible portfolio P&L. The
historical availability assumption, bar OHLC execution, simple cost model,
funding assumption (zero), and no portfolio allocation make this unsuitable
for profitability inference. Data windows are recent, too short and not
locked OOS; the legacy engine was not replayed on the same opportunity grid.
No statistical inference, confidence interval, or comparison is claimed.
The result is *negative*, so there is certainly no basis to claim an edge.

## Verified

- Isolated read-only AWS run of the script: exit code 0.
- Full offline regression in isolated staging: **643 passed in 8.26s**.
- No merge, deploy, trading or production modifications.

## Mandatory next steps

1. Download, verify and version months of continuous 1m/5m SOL/XRP data,
   actual funding and historical fee assumptions; register data snapshots.
2. Lock train/validation/calibration and two non-overlapping OOS windows
   before fitting or selecting strategies.
3. Model a common capital allocation, one position at a time per market,
   full stop/target ambiguity, funding and timeouts; reject overlapping
   economic events.
4. Run the old and new engine on exactly the same opportunity grid and
   identical execution/cost assumptions.
5. Require at least 200 independent OOS trades, eight weeks OOS, positive
   net expectancy in two locked periods, a credible weekly block-bootstrap
   lower bound and robust positive A/B uplift before considering replacement.
6. Validate schema, independent verifier, Telegram shadow-mode, dedup,
   kill-switch, rollback and manual release approval.

**Decision: NOT_READY.** No claimed profitability.
