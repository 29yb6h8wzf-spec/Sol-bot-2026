# Signals V2 — evidence and replacement release gate (2026-11-10)

**Decision: NOT_READY / research only.** This document is a fail-closed review gate, not an approval to deploy, merge, trade, or replace the legacy engine.

## Evidence inventory
- Public replay diagnostic: `signals_v2/REAL_DATA_DIAGNOSTIC_20261110.md`; Binance public 1m/5m candles, 1,000 each per symbol, 150 eligible decision timestamps per symbol.
- SOL: 22 overlapping hypotheses, 13 STOP, 5 TARGET, 4 TIMEOUT, sum -8.6823 net R.
- XRP: 19 overlapping hypotheses, 15 STOP, 1 TARGET, 3 TIMEOUT, sum -15.7739 net R.
- These are **not** independent portfolio trades, valid OOS estimates, or A/B results. Funding was assumed zero. Do not infer win rate, PF, MDD, expectancy, CI or profitability from these overlapping samples.
- Prior offline regression reported 643 passing tests. Later changes and latest GitHub Actions checks must be verified separately; a missing commit status is not a pass.

## Locked study protocol (register before execution)
1. Pin immutable code SHA, UTC start/end, data source and file SHA-256; document all missing minutes and excluded periods. Prefer 24 months of 1m/5m SOLUSDT and XRPUSDT Binance USD-M data, or disclose shorter coverage. Use historical funding events, mark/index where needed, and actual exchange fee assumptions.
2. Enforce close-time availability, next executable entry, consistent bid/ask/slippage assumptions, conservative intrabar STOP/TARGET tie-break, 4h maximum holding, no future leakage, and nonoverlapping per-symbol positions. Record skipped signals and reasons.
3. Lock two disjoint OOS periods of at least eight total weeks, independent of training, calibration and model selection. No retuning after OOS inspection. Count at least 200 independent OOS trades before any positive claim.
4. Evaluate simple rules and ML on the identical locked partitions. Calibrate ML only on a disjoint calibration period with enough positive and negative labels; otherwise disable calibration and label INCONCLUSIVE.
5. Replay legacy and V2 on identical SOL/XRP timestamps, data snapshots, entry/exit engine, funding, fees, slippage, risk limits and capital accounting. Include abstentions, opportunity counts and signal deduplication. Report signal count, independent trades, win rate, net expectancy, profit factor, max drawdown, net OOS return and weekly block-bootstrap 95% CI, by symbol, side, regime and OOS period.
6. Report paired weekly A/B net uplift with a bootstrap CI; distinguish significance from mere increase in signal count. Require positive net expectancy in **both** locked OOS periods and a defensible positive lower confidence bound before considering an edge.

## Replacement compatibility (design only, do not activate)
- Versioned `signals-v2/v1` signal schema with UTC closed-candle timestamp, symbol, side, strategy, evidence, source version and stable dedup key; reject unknown versions and incomplete payloads.
- Independent verifier must remain authoritative; never route raw research scores directly to execution.
- Telegram shadow feed must be separately namespaced, tagged non-actionable and deduplicated; legacy notifications remain untouched.
- Shadow-mode compare decisions and latency without orders; preserve kill-switch, existing risk gates, monitoring, audit trail and reversible rollback to legacy.
- Test schema compatibility, malformed payload rejection, replay idempotency, missing candles, stale signals, rollback and manual approval before any cutover.

## Release decision
- Profitability OOS established: **NO**.
- Fair paired A/B improvement established: **NO**.
- End-to-end replacement compatibility and safety validated: **NO**.
- **READY_TO_REPLACE: NO — NOT_READY.** No merge, deploy, cutover, demo or live orders authorized.
