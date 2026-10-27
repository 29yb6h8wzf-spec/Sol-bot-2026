# SignalPilot — Binance USDT-M Futures Python foundation

**PAPER ONLY.** Reads public Binance USDT-M perpetual OHLCV through ccxt.binanceusdm. Does not load API keys, authenticate, create/cancel orders, set leverage or touch exchange balances. TRADING_MODE=live exits immediately. Existing Cloudflare/Telegram alerts are unchanged.

## Setup (Linux/macOS or WSL, Python 3.11+)

1. Create and activate a Python virtual environment: python -m venv .venv
2. Activate it: source .venv/bin/activate
3. Install dependencies: pip install -r futures-requirements.txt
4. Copy .env.futures.example to .env and edit settings if needed.
5. Run tests: python -m unittest discover -s tests -p 'test_futures_paper*.py'
6. Run one paper scan: python -m futures_engine

Run python -m futures_engine once per closed 15-minute candle using a local scheduler. Paper state persists in paper-ledger.json; back it up. The CLI holds a nonblocking OS file lock across ledger load, exit evaluation, risk sizing and entry persistence. A second runner fails closed. Use a local filesystem; network filesystem lock semantics are not supported. Native Windows is unsupported; use WSL. Binance Futures public endpoints may be regionally unavailable; the engine fails closed and never substitutes Kraken Spot.

## Strategy and paper risk

- One symbol, default BTC/USDT:USDT 15m; at least 202 closed contiguous candles.
- LONG on EMA(50) crossing above EMA(200) with RSI(14) below 55; SHORT on reverse crossing with RSI above 45.
- 2% simulated stop, 4% simulated target, 2x maximum notional/equity, 1% maximum estimated stop loss including modeled fees/slippage.
- 5% UTC calendar-day realized-equity breaker, also limits remaining daily loss allowance. It is **not** a rolling 24-hour exchange-account drawdown.
- Paper stop/target are checked on subsequent closed candles; if both are hit in one candle, assume stop first unless the opening price already crossed a target. A stop gap fills at the worse opening price; target gaps receive no favorable price improvement. One open paper position, deduplicated signals, precision and minimum amount checks; no rounding dust up.

## Limitations before live trading

Paper positions have **no exchange-side protective orders**. Stop/target fills, fees, slippage and gap behavior are approximations. No funding, liquidation modeling, account-wide portfolio exposure, actual live order reconciliation. Paper exit evaluation is limited to fetched recent candles. A persisted cursor detects missing exit history after downtime and stops the scan without closing or replacing the position. Restore the complete missing history before continuing; automated historical backfill is not implemented. Before live execution, a separately approved phase must add native exchange-side reduce-only protective orders, order reconciliation, margin/position-mode checks, funding accounting, extensive Binance Futures testnet integration.

No API keys are needed. Never put secrets in GitHub, screenshots, Telegram or Actions. Future keys should be trade-only, withdrawals disabled, IP restricted and minimally privileged.

## Ledger integrity and accounting conventions

- Each ledger is bound to one symbol and timeframe. Changing either requires a separate ledger. Existing ledgers containing trades without market identity are rejected: archive them, do not silently assign their positions to the configured symbol.
- Writes use a unique temporary file, file fsync and atomic replacement. Keep backups; this does not guarantee survival of every filesystem/power failure.
- Exits are processed chronologically before rolling to the latest candle's UTC day. Intrabar exit times are unknown and attributed to the candle opening time. Entry is theoretical at the signal candle close, not a claim of executable historical fills. There is no latency/order-book model.
- The realized-equity breaker includes modeled round-trip costs at exit; it does not track unrealized drawdown or debit costs at entry. Rates are frozen in each position. Price gaps can exceed both the estimated 1% trade budget and the 5% daily threshold. These limits size/refuse new entries; they do not guarantee a maximum realized loss.
- Nonfinite/invalid OHLCV and unsafe numerical configuration fail closed. Only USDT-settled linear perpetuals are accepted. No credentials, private account data, order endpoints or Telegram state are used.

## Regression coverage

`python -m unittest discover -s tests -p 'test_futures_paper*.py' -v`

Offline tests cover long/short stop gaps, ambiguous stop/target candles, UTC rollover, repeated scans, restart cursors, missing history, market identity, cross-process lock contention and release, atomic-write failure, frozen costs, remaining daily risk, malformed/stale data, retries, and rejection of live mode before data access. CI runs Python 3.11, 3.12 and 3.13. These tests do not certify exchange connectivity or strategy profitability.
