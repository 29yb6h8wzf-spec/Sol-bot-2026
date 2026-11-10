# Signals V2 — historical data acquisition gate (2026-11-10)

**Status: BLOCKED / NOT_READY.** This is an acquisition and validation specification, **not** a claim that historical data was downloaded. No orders, production, legacy strategy edits, or deployment.

## Required data and coverage
- SOLUSDT and XRPUSDT, Binance USDⓈ-M futures, 1m and 5m OHLCV; target 24 months ending before the first locked OOS window. Record actual first/last UTC timestamps and missing intervals separately for each symbol/timeframe.
- Prefer official Binance public archives at https://data.binance.vision/?prefix=data/futures/um/monthly/klines/ and https://data.binance.vision/?prefix=data/futures/um/daily/klines/ ; use the public API only to repair explicitly logged gaps. Public funding history: https://fapi.binance.com/fapi/v1/fundingRate (paginated with recorded start/end).
- Record raw ZIP SHA-256, exchange-provided checksum where available, extracted row count, timestamp min/max, exact download URL, UTC download time, schema version, and any repaired segments. Keep raw files outside Git and do not commit multi-month price data.
- Reject duplicate, nonmonotonic, off-grid, missing or not-yet-closed candles; validate OHLC consistency, nonnegative volume, 1m/5m reconciliation and UTC boundaries. Never silently forward-fill prices, funding, or missing bars.
- Historical candle-close availability is an **optimistic reconstruction**, not evidence of contemporaneous availability or executable close fills. Entries must be no earlier than the next executable bar; log bar ambiguity and use conservative stop-first policy.
- Funding must use timestamped actual rates at applicable payment events; missing funding or fees => INCONCLUSIVE for net P&L. Fee/slippage assumptions and sensitivity ranges must be registered before OOS.
- Preserve hashes of raw inputs, transformed inputs, code commit, configuration and output artifacts in a run manifest. Pin train/validation and two disjoint OOS intervals before fitting; keep OOS untouched until final evaluation.

## Completion criteria for step 1
1. Four OHLCV datasets (2 symbols × 2 timeframes) with checksums, complete UTC coverage manifests, and independently validated candle continuity.
2. Funding coverage and documented fee/slippage provenance and gaps.
3. Reproducible offline ingestion into `signals_v2.historical.historical_rows` with no missing segments hidden by interpolation.
4. Explicit GO/NO_GO report for whether the dataset can support 8+ weeks of locked OOS and 200 independent trades (trade count can only be established after replay).

**Current evidence:** `REAL_DATA_DIAGNOSTIC_20261110.md` documents only 1,000 recent candles per timeframe per symbol; it is not sufficient. Do not mark this gate complete until all required manifests and files exist.
