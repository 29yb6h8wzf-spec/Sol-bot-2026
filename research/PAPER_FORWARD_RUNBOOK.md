# SignalPilot: isolated forward Paper monitor (NOT deployed)

This branch contains a **one-shot** public-market scanner, not a running
service. No GitHub schedule, systemd timer, EC2 deployment, production merge,
Binance order API, exchange credentials, or SQS publisher is enabled here.

## One manual run in an isolated research environment

Use a separate research working directory with Python 3.11 and `ccxt`
installed. Ensure outbound public Binance USDT-M OHLCV is available. If the
provider returns HTTP 403 or 451, record `BLOCKED` and stop; do not bypass
regional restrictions or substitute demo/private order endpoints.

```bash
python -m research.paper_forward_once \
  --snapshot-dir /tmp/signalpilot-forward-snapshots \
  --db /tmp/signalpilot-forward-paper.sqlite3
```

This fetches **public closed candles only** for SOL and XRP, captures immutable
scanner+5m+4h bundles, and processes eligible older snapshots against later
closed 5m candles. The command exits after one pass. A separate scheduler
could invoke it every 5 minutes **only after deployment approval**. Keep
snapshot files and SQLite DB on persistent isolated storage before scheduling.

## Safety and evidence boundaries

- Scan and verification run on the same exact closed candle histories.
- `captured_at_ms` must be in the window after the signal candle closes and
  before the next candle closes. The local timestamp is *not cryptographic
  evidence* of capture time; independently retained scheduler logs or
  timestamped artifacts are needed for trustworthy forward claims.
- If the scan was captured after the next 5m candle opened, simulated entry
  is delayed to the following candle open. The first post-signal candle cannot
  be filled retroactively.
- Missing data, gaps, unclosed candles, or a >0.5% move from signal close
  to the eligible entry open block a paper fill. The SQLite store is local.
- Risk sizing uses at most $150 capital, 2x leverage, and $1.50 estimated
  stop loss including the model's fees and slippage.
- The current Paper simulation does not yet implement all live execution
  checks (exchange filters, position portfolio limits, funding, real fills,
  connectivity). Passing these tests does **not** authorize real orders.
- A historical fixture test is not a live forward trade. No profitability
  claim follows from a successful historical replay.

## Public data access finding (2026-11-09)

The GitHub-hosted runner attempted a read-only public SOL/XRP scan and
received **Binance HTTP 451 (restricted location)** for both symbols.
It produced no live scanner snapshots or Paper orders. The scheduled/network
smoke job was removed after this evidence; do not proxy or evade restrictions.
The read-only Binance connector supplied a separately captured SOL/XRP closed-
candle snapshot at 20:23:20 UTC, committed at 20:23:22 UTC, before the next
5m candle closed at 20:25 UTC. The offline scanner test evaluates that saved
input without network. This is a captured data snapshot, **not** a running
forward scanner or an automatically executed Paper trade. The data connector
is not integrated into the isolated scheduler.

## Tests

```bash
python -m pytest -q tests/test_paper_forward_capture.py
python -m pytest -q tests/test_paper_auto_replay.py
```

No automated production deployment or merge is part of this PR.
