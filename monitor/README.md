# SignalPilot Scan Desk

Private Hebrew dashboard for the scheduled Kraken Spot research scanner in cloudflare/worker.js. Separate from the USDT-M execution engine. The browser polls the same-origin /api/scans every 30 seconds while visible. Prices come from the breakout diagnostic's closed candle. Missing prices, historical slots and partial runs are visible. Only the last 24 five-minute slots ending at the latest receipt are read.

The separate service/feed.mjs Worker binds SIGNAL_STATE to the scanner KV namespace and accepts authenticated GET /v1/scans. Its routes only read health:latest and the previous 23 health:cron slots. Configure READER_TOKEN as a server-side secret on both the private Site and the reader. The reader has no cron or trading credentials. The Site's owner-only access boundary protects the same-origin API.

Run node --test service/feed.test.mjs and node build.mjs here. Deployment output is dist/server/index.js. The private Site hosting manifest is supplied by the hosting checkout.
