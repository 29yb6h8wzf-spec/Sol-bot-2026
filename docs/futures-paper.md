# SignalPilot — Binance USDT-M Futures Python foundation

**PAPER ONLY.** Reads public Binance USDT-M perpetual OHLCV through ccxt.binanceusdm. Does not load API keys, authenticate, create/cancel orders, set leverage or touch exchange balances. TRADING_MODE=live exits immediately. Existing Cloudflare/Telegram alerts are unchanged.

## Setup (local Python 3.11+)

1. Create and activate a Python virtual environment: python -m venv .venv
2. Activate it: source .venv/bin/activate (Windows: .venv\\Scripts\\activate)
3. Install dependencies: pip install -r futures-requirements.txt
4. Copy .env.futures.example to .env and edit settings if needed.
5. Run tests: python -m unittest discover -s tests -p 'test_futures_paper.py'
6. Run one paper scan: python -m futures_engine

Run python -m futures_engine once per closed 15-minute candle using a local scheduler. Paper state persists in paper-ledger.json; back it up. Only one instance per ledger (no cross-process locking). Binance Futures public endpoints may be regionally unavailable; the engine fails closed and never substitutes Kraken Spot.

## Strategy and paper risk

- One symbol, default BTC/USDT:USDT 15m; at least 202 closed contiguous candles.
- LONG on EMA(50) crossing above EMA(200) with RSI(14) below 55; SHORT on reverse crossing with RSI above 45.
- 2% simulated stop, 4% simulated target, 2x maximum notional/equity, 1% maximum estimated stop loss including modeled fees/slippage.
- 5% UTC calendar-day realized-equity breaker, also limits remaining daily loss allowance. It is **not** a rolling 24-hour exchange-account drawdown.
- Paper stop/target are checked on subsequent closed candles; if both are hit in one candle, assume stop first. One open paper position, deduplicated signals, precision and minimum amount checks; no rounding dust up.

## Limitations before live trading

Paper positions have **no exchange-side protective orders**. Stop/target fills, fees, slippage and gap behavior are approximations. No funding, liquidation modeling, account-wide portfolio exposure, cross-process locking or actual live order reconciliation. Paper exit evaluation is limited to fetched recent candles, so this prototype must be run regularly and should not be left unattended with an open simulated position. Before live execution, a separately approved phase must add native exchange-side reduce-only protective orders, order reconciliation, margin/position-mode checks, funding accounting, persistent locking and extensive Binance Futures testnet integration.

No API keys are needed. Never put secrets in GitHub, screenshots, Telegram or Actions. Future keys should be trade-only, withdrawals disabled, IP restricted and minimally privileged.
