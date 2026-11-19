# SOL/XRP OHLCV source verification — 2026-11-19

Research-only data-provenance checkpoint. No live trading or production changes.

## Verified inventory
- AWS S3 bucket `signalpilot-ingress-artifacts-514349355336`, prefix `research/stage3/2026-11-11/`, contains `exp003.zip`, `exp004.zip`, `seal_candidate_v2_1.zip`.
- ZIP central directory of `exp004.zip` lists `exp004/exp004/fetch_archives.py`, `data.py`, `config.py`, and `results/HOW_TO_RUN.md`. These entries are deflate-compressed.
- The archive inventory does **not** include raw 5m/4h SOL/XRP OHLCV series.
- A read-only file-name inventory of the active EC2 instance did not identify matching raw candle files in inspected directories. The production checkout does not contain the new replay module.

## Unverified; must not assume
- The fetcher's upstream source, date coverage, symbol identifiers, timeframe, checksum validation, or output format.
- Whether the original 24-month data is recoverable from the upstream source.
- Whether a 4h series is derived from closed 5m candles with correct UTC boundaries.
- Any 70–84 score-band counts or profitability claims.

## Required before historical replay
1. Read the exact `exp004/exp004/fetch_archives.py`, `data.py`, `config.py`, and `results/HOW_TO_RUN.md` contents; review URL allowlist and data licensing.
2. Retrieve a **read-only** copy of the source OHLCV data to an isolated research workspace; never write into the running bot checkout.
3. Verify symbol and market (Binance USDT-M SOL/XRP), UTC timestamps, 5m cadence, contiguous bars, OHLC bounds, positive prices, nonnegative volume, and checksum/provenance.
4. Build closed 4h bars or validate the provided 4h bars; forbid future leakage.
5. Run `research_closed_candle_score_replay` and publish only aggregate score-band counts. This is **not** a trading backtest; evaluate costs and locked OOS separately.
