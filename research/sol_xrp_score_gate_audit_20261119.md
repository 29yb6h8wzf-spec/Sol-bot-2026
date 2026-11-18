# SOL/XRP V2 score-gate audit (research only)

Reviewed source: `strategies.py` and `futures_engine/verified_strategy_scan.py` on `research/v3-provenance-semantics-20261118`.

## Confirmed from code
- The scanner requires an integer score >= 85 before independent candidate verification.
- `RSI_BOLL` uses `65 + max(0, 45-rsi)/3` for LONG and `65 + max(0, rsi-55)/3` for SHORT. Since RSI is between 0 and 100, its maximum score is 80. This strategy cannot reach the 85 gate.
- `MACD_VOLUME` uses `65 + min(20, volume_ratio*10)`; it requires volume_ratio >= 2 to reach 85, even though the entry condition allows volume_ratio >= 1.2.
- `EMA_ADX` uses `60 + min(15, ADX-20) + min(15, volume_ratio*8)`; its ability to reach 85 depends on both ADX and volume.
- Score is a heuristic, not a win probability or evidence of net profitability.

## Observed live database (read-only inspection)
- SOL and XRP research scans: 4,463 per symbol in the inspected snapshot.
- SOL: 67 scans containing 70 candidates at 85+.
- XRP: 60 scans containing 61 candidates at 85+.
- Deployed scan records lack `scan_diagnostics`; empty `rejected_candidates` does NOT establish zero rejected setups.
- These are research candidate counts, not executed trades.

## Next research experiment (not authorized for production)
Run a shadow-only score distribution on closed 5m/4h candles, reporting setup counts by strategy, direction and score band (below 70, 70-79, 80-84, >=85), with separate verification-rejection and no-setup counts. Do not lower the gate or change order authorization. Evaluate any proposed threshold change on locked out-of-sample data, including fees and slippage. No deployment, merge, live orders or retrying Telegram delivery.
