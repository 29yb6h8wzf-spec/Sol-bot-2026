# SignalPilot Production Architecture and Release Gates

Status: architecture proposal, **not production authorization**.

## Components and trust boundaries

1. **Market adapter**: Binance USDT-M public OHLCV/mark-price/funding via CCXT or bounded REST. Closed candles only, strict timestamps, symbol allowlist BTC/ETH/SOL/XRP, timeouts, rate limits, bounded retries. Network failure => no signal.
2. **Signal engine**: deterministic strategy evaluation; >=85 score is a screening threshold, **not a success probability**. Idempotency key (exchange, symbol, timeframe, closed_candle, strategy, direction). No order access.
3. **Research shadow**: Premiss backtest receipts and AlgoVault BUY/SELL/HOLD with provenance, timestamps, and symbol checks. Provider disagreement/absence recorded, never overrides verifier or risk. Do not use historical performance as live authorization.
4. **Independent verifier**: fresh Binance closed candles, recompute strategy and score, reject stale or mismatched payloads. Telegram/SQS messages are untrusted.
5. **Risk planner**: derive entry, stop, target, quantity from trusted market data; use Decimal and exchange precision. Per-trade loss <= $1.50; allocation cap $150; leverage <=2x; daily loss cap <=5%; fees, slippage, funding and margin must be budgeted; stale or unreconciled account => block.
6. **Paper execution**: separate simulation-only adapter, durable idempotent ledger and lifecycle (planned/open/partial/closed/cancelled); deterministic fills, stop/target collisions, modeled fees/slippage. Explicit mode PAPER. No live order path.
7. **Operations**: AWS SQS/inbox durable delivery, DLQ, health/cron receipts, Telegram notifications, metrics, audit trails, secret storage, bounded queues, rollback. Cloudflare Kraken research and AWS Binance Futures flows remain distinct until reconciled.

## Invariants

- No Binance create_order, order cancellation or account-mutating call in research, verifier, risk, or paper pathways.
- Signal source and third-party confidence never authorize execution.
- Exactly-once economic effect for each idempotency key even after restart/retry.
- Fail closed on API failure, clock skew, stale candles, missing or inconsistent balance, non-finite values, stop/target inversion, excessive exposure, funding/fee uncertainty.
- Production-ready requires observed evidence, not a percentage estimate.
- Live trading remains disabled pending a separate explicit approval and independently reviewed release gates.

## Dynamic task board

| ID | Workstream | State | Exit evidence |
|---|---|---|---|
| 1 | Architecture/contracts | In progress | Document reviewed + interface tests |
| 2 | Binance data API | Pending | Closed candle/funding source parity, timeout/retry tests |
| 3 | Signal engine | Pending | Deterministic 85+ and idempotency tests |
| 4 | Premiss/AlgoVault | Pending | Automated read-only ingestion, provenance and incremental-value evaluation |
| 5 | Risk management | Pending | Stop-loss/margin/day-loss/fee adversarial tests |
| 6 | Error handling | Pending | Network failure, restart and DLQ recovery tests |
| 7 | Paper execution | Pending | Reconciled open-to-close simulated trade |
| 8 | Backtesting | Pending | Out-of-sample, fees/slippage, reproducible runs |
| 9 | Integration/E2E | Pending | Cloudflare/AWS transport + ledger reconciliation |
| 10 | Release | Pending | 24h stable telemetry, security review, rollback drill |

## Current known blockers

- AWS DEMO account reconciliation and execution authorization are blocked; no demonstrated complete paper trade.
- Cloudflare->AWS transport / AWS->Cloudflare research delivery needs explicit path-by-path verification; do not conflate separate flows.
- External research shadow adapter exists but has no automatic provider polling.
- EC2 checkout contains untracked and modified files; do not overwrite without inventory.
- GitHub checks and Cloudflare Workers Build are not sufficient evidence of production runtime.

## Next engineering task

Introduce typed interface contracts for market snapshots and research observations with offline unit tests, then build a read-only Binance market adapter against those contracts. Never deploy or enable real orders as part of this change.
