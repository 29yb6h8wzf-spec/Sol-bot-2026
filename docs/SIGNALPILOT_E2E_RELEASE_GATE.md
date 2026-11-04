# SignalPilot — End-to-end release gate (2026-11-04)

## Objective
Prove a single independently verified Binance Futures signal travels from scanner to durable inbox, risk planning and demo-only execution with audited fills. **Do not enable live trading.**

## Verified baseline
- AWS EC2 i-03f8395a7b6d8760e, il-central-1, /opt/signalpilot; SQS consumer and signal inbox services active at audit.
- 27/27 focused safety, preflight and portfolio risk tests passed on EC2.
- Isolated local inbox test accepted a synthetic signal, rejected a duplicate and blocked an unverified signal; no orders sent.
- SQS metrics previously showed zero messages sent over Nov 3–4 interval; Cloudflare-to-SQS delivery not proven.
- Cloudflare scheduled Worker sol-bot-2026 cron */5; account monitor warning binance_http_403 observed. Do not equate this with scanner failure without logs.
- demo_order_planner.py exists on EC2 but is not tracked in the current EC2 checkout. It is indicative/read-only.
- demo-risk-monitor-status.json reported BLOCKED / UNATTRIBUTED_HISTORICAL_FILLS, allocation_ledger_reconciled=false, execution_authorized=false.
- demo-risk-account.json absent. demo-account-observation.json exists but is observation-only, not authorization.
- Many EC2 files are untracked and futures_engine/__main__.py modified. Preserve and reconcile; never overwrite blindly.

## Execution plan and release gates
1. **Inventory/source of truth:** collect sanitized file hashes, service entrypoints, git diff and dependency map from EC2; compare to GitHub. Keep credentials, database content, API keys, tokens and runtime observations out of git.
2. **Transport:** establish an isolated test queue or mocked SQS consumer. Prove producer -> transport -> consumer -> durable inbox with IDs, timestamps, duplicate and retry behavior. Never spoof production verified signals.
3. **Verifier:** use real fresh Binance USDT-M closed candles; verify >=85 score independently and record source, candle, strategy, failure reason. If API unavailable, report BLOCKED, not success.
4. **Planner:** join verified proof with independently fetched candles and exchange filters; produce entry/stop/target/quantity; enforce $150 max allocation, 2x leverage, <=$1.50 planned risk before fees, and fees/slippage checks.
5. **Reconciliation:** reconcile historical DEMO fills/positions and account exposure before producing a trusted fresh snapshot. Do not force APPROVED or bypass guard.
6. **Demo execution:** only after above gates, test isolated demo bracket entry/exit, duplicate prevention, protective orders, and journal reconciliation. No live orders.
7. **Deployment:** run full test suite, document exact commit, deploy steps, rollback, Cloudflare cron receipt, SQS send/receive counts, and end-to-end evidence.

## Definition of done
One real market-derived eligible signal (or explicit documented no-signal outcome) is traced with a stable correlation ID across every component; demo order lifecycle proven only when all safety and reconciliation gates pass. No live trading without a separate explicit release approval.

## Next concrete change
Add non-trading integration tests for consumer/inbox and verifier/planner, then compare EC2-only modules against repository before copying any production code.
