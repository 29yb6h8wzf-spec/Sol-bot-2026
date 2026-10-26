# Signal scan reliability — October 2026

## What this change does
- Emits machine-readable `SCAN_EVENT` JSON for every scheduled symbol scan, including reasons for no breakout, indicator candidate counts, rejected stop distances, and stale-candle skips.
- On stale scans, lists recently closed candle opening timestamps **for investigation only**. It does not replay missed historical entries as current trades.
- Adds a smoke test for the diagnostics.

## What this change does NOT do
- It does not guarantee a five-minute schedule. GitHub Actions cron can run late or be skipped.
- It does not change entry thresholds, execute orders, or prove any signal profitable.
- It does not backtest missed signals; that needs time-aligned 4h data and realistic fills.
- It does not change Telegram buttons.

## How to verify
1. Merge the PR after the validation workflow passes.
2. Open Actions → SOL Telegram Alerts → latest scheduled run → each symbol job.
3. Search logs for `SCAN_EVENT`. Expect `no_breakout_setup`, `multi_candidates`, or `skip_stale_*` on each scheduled scan.
4. Compare consecutive scheduled run timestamps. Gaps over 5 minutes are scheduler gaps, not necessarily zero market opportunities.
5. Collect at least 24–72 hours of logs before deciding whether the strategy is too selective.

## Reliable scheduling — next deployment
For dependable near-five-minute scanning, move scheduling to a dedicated always-on worker or external cron with persistence and idempotent per-candle processing. GitHub Actions scheduled workflows cannot provide a five-minute execution guarantee. Do not enable a second scheduler before disabling the original, or duplicate notifications may result.
