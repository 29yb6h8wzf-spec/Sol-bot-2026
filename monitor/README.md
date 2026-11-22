# SignalPilot Live Desk

Private Hebrew monitoring dashboard for the deployed Binance USD-M breakout engine (SOL/XRP). Reads actual execution journal outcomes and fill-notification records; it does not rerun a research scanner or infer per-symbol checks. Live engine statuses, missing minutes, stale telemetry, fill prices and notification delivery states are shown. Open-position balances and PnL are unavailable and not inferred from ledger state.

## Read-only publisher

`service/publisher.py` reads `signalpilot-breakout-live.service` journal records (last two hours, up to 120 outcomes) and opens the execution and notification SQLite files with `mode=ro`. It has no exchange client or order calls. The independent systemd service/timer publishes every 30 seconds. It reads its write-only ingest token from SSM SecureString `/signalpilot/dashboard/ingest` in `il-central-1`. The existing EC2 role provides access; no IAM changes required. Install under `/opt/signalpilot-dashboard/` and units under `/etc/systemd/system/`.

## Private feed

`service/feed.mjs` and `service/live.mjs` form the separate feed Worker. POST `/v1/live` requires `LIVE_INGEST_TOKEN`, validates and whitelists telemetry, and stores `dashboard:binance:live` in SIGNAL_STATE with a 24-hour TTL. GET requires the independent `READER_TOKEN`. The old research GET route remains available for compatibility, but the Site exclusively requests `/v1/live`. Tokens stay in runtime secret storage, never browser code.

The private Site proxies its same-origin `/api/scans` to the live feed. The browser polls every 30 seconds while visible and flags data collected over two minutes ago or an engine outcome over three minutes old. KV propagation may add delay. Delivery labels reflect the notification journal, not a fresh Telegram receipt check.

Run `node --test service/live.test.mjs service/feed.test.mjs`, then `node build.mjs`. Deploy `dist/server/index.js` using the hosting manifest. Stop the independent `signalpilot-dashboard.timer` to disable telemetry without changing the trading engine.
