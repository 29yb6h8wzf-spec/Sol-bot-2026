# Copy-trader reverse-engineering research gate

This workflow is **offline research only**. It must never enable live orders or alter production services.

## Parallel tracks

1. **Source acquisition:** Find public Bybit/Bitget/Binance trader profiles with verifiable 30/90-day drawdown, leverage and at least 100 closed trades. Do not substitute market-wide recent trades for the trader's own positions. Bybit market /v5/market/recent-trade is **not** a copy-trader history endpoint. Kopyon offers positionHistory but needs an API key; don't assume access.
2. **Fingerprint:** Export a CSV with symbol,side,entryPrice,closePrice,openedAt,closedAt. Run `python tools/copy_trader_fingerprint.py path/to/history.csv`. Optional leverage,roi,margin are not enough to reconstruct wallet drawdown.
3. **Rule inference:** Join the timestamps to *closed* 5m/1h/4h market candles. Evaluate trend-pullback, breakout, mean-reversion hypotheses; include a no-trade baseline. Require a temporal 70/30 split, count matches with tolerance and false-positive entries, and prevent lookahead.
4. **Execution validation:** Simulate fees, slippage, funding, realistic margin constraints and no-overlap. Require positive out-of-sample expectancy, sufficient trades, and Paper evidence before proposing any change to active signals.

## Data limitations

Do not equate copy-trader displayed ROI with actual net follower PnL. Public leaderboards can hide positions or omit intratrade drawdown. Avoid survivorship bias and cherry-picking a top recent winner. Never infer exact stop/target from closed trades alone. Require a complete position history and equity time series to estimate portfolio maximum drawdown.

## Current status

Candidate source: Bybit copy-trading leaderboard. No trader's full historical closed-position CSV has yet been verified or imported. The fingerprint tool is ready for an authentic export; no trader strategy has been replicated or proven profitable.
