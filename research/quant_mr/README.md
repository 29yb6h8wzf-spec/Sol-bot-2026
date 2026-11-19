# SignalPilot Quant Mean Reversion — SOLUSDT / XRPUSDT

This is a **research and safety-testing prototype**, not a production-ready trading system. No live or demo exchange orders were sent while preparing these files.

## Files

- `signalpilot_quant_mr.py`: 15-minute VWAP mean-reversion scanner and a **disabled-by-default** CCXT execution path.
- `test_signalpilot_quant_mr.py`: unit tests of signal rules, risk guards, order state, stop/TP, and emergency recovery.
- `backtest_signalpilot_quant_mr.py`: public-data-only, chronological 70/30 research backtest of a **shared $150** simulated portfolio.
- `test_backtest_signalpilot_quant_mr.py`: synthetic, deterministic backtest tests.
- `requirements_signalpilot_quant_mr.txt`: Python dependencies.

## Install and test

Use Python 3.11+ on Linux or macOS (the bot uses `fcntl` to prevent duplicate instances). For Windows use WSL.

```bash
python -m pip install -r requirements_signalpilot_quant_mr.txt
python -m pytest -q test_signalpilot_quant_mr.py test_backtest_signalpilot_quant_mr.py
```

The offline unit tests can run without `ccxt`; `ccxt` is **required** to fetch public Binance data or run the scanner. All exchange interactions in the unit tests are mocked.

## Scanner: read-only by default

```bash
SIGNALPILOT_MODE=dry_run python signalpilot_quant_mr.py
```

`dry_run` scans real public market data, logs conditions and hypothetical signals, and **never submits orders**. It does not track hypothetical position PnL. It requires public Binance endpoints to be reachable from your location.

The bot checks for a `STOP_TRADING` file in its working directory. When present, it stops opening new positions; reconciliation of existing positions continues in live mode.

**Do not enable `SIGNALPILOT_MODE=live` yet.** The live execution path is not validated against the currently installed CCXT build or a Binance Demo account. An exchange rejection, API change, or network failure could leave a position unprotected. Never put real credentials into source files.

## Historical research

```bash
python backtest_signalpilot_quant_mr.py --days 30 \
  --save-snapshot market_snapshot.json --output historical_report.json

# Re-run exactly the same saved data, without any network requests:
python backtest_signalpilot_quant_mr.py \
  --snapshot market_snapshot.json --output historical_report_repeat.json
```

The downloader uses only Binance public USD-M futures trade and Mark Price candles, with no API keys or order endpoints. It will fail rather than work around a regional Binance API restriction.

Backtest assumptions: $150 shared wallet; 3x maximum leverage; margin per position <=5% of wallet; one position per symbol; at most two open; next 15-minute candle open used for hypothetical entry; Mark Price candles for STOP/TP detection; 1.5% SL and >=3% TP after tick rounding; taker fee **0.05% per side** and assumed slippage **0.05% per side**; stop-first when both triggers hit within a candle; gap >0.5% skips entry; daily 5% simulated equity circuit breaker. It **does not include funding, liquidation, exchange order-book impact, partial fills, or live execution failures**. Results are historical simulation, not forward Paper evidence.

## Safety controls in the execution prototype

- Uses Isolated Margin and verifies a 3x leverage acknowledgment before any entry (this differs from the project's earlier 2x ceiling).
- Calculates MARKET order size from current USDT wallet balance, max 5% margin, with exchange min notional, step size, and price tick rules.
- Allows only one-way mode, one position per symbol, and no unmanaged existing positions before entry.
- Sends STOP_MARKET then TAKE_PROFIT_MARKET via the conditional Algo Order endpoint using `MARK_PRICE` and `closePosition=true`.
- **Binance does not guarantee native OCO sibling cancellation for these two independent orders.** Reconciliation removes leftover bot-owned conditional orders after the position closes. It runs approximately every four seconds while the process is alive.
- If bracket placement or verification fails, attempts a reduce-only emergency flatten, cleans up bot-owned Algo orders, preserves a pending marker, and requires manual reconciliation.
- Uses SQLite for candle deduplication, position state, and a UTC daily drawdown baseline. Checks both wallet and margin equity, including unrealized PnL, before opening new positions.

## Required before production

1. Validate the exact CCXT version and Binance Algo Order API parameters with a **dedicated Binance Futures Demo** account; test both sides, partial fills, timeouts, orphaned conditional orders, restart recovery, and a simulated outage.
2. Run an independent, forward-captured Paper experiment with a persistent authorized market-data feed, timestamps, and audit logs.
3. Validate the strategy on substantially more out-of-sample data including funding and realistic fees; test portfolio drawdown and a kill switch.
4. Obtain separate approval for any merge/deployment or live trading. No merge, AWS deployment, or real order is part of this package.

## Initial research observation (not reproducible from this bundle alone)

A preliminary read-only connector analysis of 3,000 Binance 15m trade and mark candles per symbol, spanning approximately 2026-10-09 to 2026-11-09, simulated each symbol **separately** with its own hypothetical $150 wallet (not the shared-portfolio backtester above). In the last 30% of that sample, SOL had 5 wins and 7 losses across 12 closed trades (about +$0.45), while XRP had 0 wins and 12 losses (about -$4.50), before funding. Those exploratory numbers are not validated by the downloadable Python backtester, and must not be treated as proof of expected returns. The saved-data portfolio backtest should be run before drawing conclusions.