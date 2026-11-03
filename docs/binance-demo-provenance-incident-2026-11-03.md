# Binance DEMO provenance incident — 2026-11-03 (read-only audit)

Status: **explained with high confidence, NOT reconciled, NOT cleared for trading**.

## Exchange evidence

The Binance USD-M DEMO account reported five fills associated with four **XRP/USDT:USDT** market orders (UTC):
- 10:31:05.679 BUY, non-reduce-only, one fill
- 10:31:08.346 SELL, reduce-only, two fills
- 14:03:49.665 BUY, non-reduce-only, one fill
- 14:03:51.395 SELL, reduce-only, one fill

All four orders were closed. The read-back client-order IDs start with `x-cvBPrNm9`, the exact default futures broker prefix of installed CCXT 4.5.91. None start with SignalPilot's required `SPDEMO-` provenance tag. The trusted demo execution registry was absent, so **none of these orders may be claimed as verified SignalPilot executions**.

## Correlated AWS execution events

AWS CloudTrail, region `il-central-1`, showed successful SSM `AWS-RunShellScript` invocations immediately preceding the order pairs:
- 10:31:00.885 UTC, command `4726eaaf-c994-41f8-a5ce-d853efdee028`, browser user-agent from an iPhone. Five seconds later, the first XRP BUY was created. The script contents were not verified, so this is a strong timing correlation, **not conclusive command-to-order attribution**.
- 14:03:44.131 UTC, command `5759f032-b55e-49bd-86f4-7dfa16d97b07`, user-agent `aws-mcp.amazonaws.com`, CloudTrail comment: "Explicit user-approved isolated Binance demo XRP bracket smoke test, no live trading". Five seconds later, the second XRP BUY was created. This is strong evidence the second pair came from an automated demo bracket smoke test.

These findings are consistent with the account owner's statement that they placed no trades manually. An SSM script or automated smoke test can place DEMO orders without the owner clicking BUY/SELL on Binance. No evidence of live-money orders was found by this audit, but live account state was not queried.

## Current safety status

The latest read-only DEMO account observation shows **no open positions**, no regular open orders, and no open algo orders in BTC/ETH/SOL/XRP. However, risk monitoring remains `BLOCKED` with `UNATTRIBUTED_DEMO_FILLS`; reconciliation remains `BLOCKED_UNRECONCILED`. Account-wide income differs from verified SignalPilot receipts, and the virtual $150 allocation is not exchange-segregated.

**Do not** backfill fake `SPDEMO-` receipts, relabel historical orders as trusted, delete audit records, disable guards, or activate live execution.

## Remediation requirements

1. Preserve historical exchange fills and CloudTrail command evidence. Treat the historical smoke tests as external/untrusted to the execution registry.
2. Use a clean, isolated DEMO account or otherwise establish a fully verified opening baseline and account-wide reconciliation, including prior history, funding and commissions.
3. Future demo executor must use deterministic `SPDEMO-` client IDs and record independently verified exchange order receipts immediately after creation.
4. Prove bracket stop/target behavior, duplicate-order prevention, reconnect recovery, account-wide loss limits, kill switch, and non-stale data with controlled DEMO execution before any live authorization.
5. Keep all execution gates fail-closed until a new explicit approval and verified independent risk assessment.

Audit performed read-only; no orders were created, canceled, or altered.
