# SignalPilot external research baseline — 2026-11-05

## Premiss reproducible research receipt

- Provider: Premiss, connected research workspace.
- Strategy ID: `4319077f-d0b1-448f-960d-f5d17559866d`
- Run ID: `fcac3cfe-ea50-41c2-af26-eed45c1190ac`
- Market: BTCUSDT, Binance, 1h closed candles
- Window: 2026-05-01 through 2026-10-31 (4416 bars)
- Rules: **SMA**(50) > **SMA**(200) => long; otherwise cash. This is **not** SignalPilot's EMA/ADX/5m futures strategy.
- Simulated initial capital: $10,000; no leverage, shorts or live orders.
- **Costs: fee_bps=0 and slippage_bps=0**. Do not present as net executable return.
- Strategy total return: +11.8874%; max drawdown: 9.1831%; 24 fills/trades; win rate: 33.3333%; profit factor: 1.7975.
- Matched buy-and-hold return: +1.4700%; max drawdown: 29.3648%.
- Run: https://app.premissai.com/app?strategy=4319077f-d0b1-448f-960d-f5d17559866d&run=fcac3cfe-ea50-41c2-af26-eed45c1190ac&tab=backtest&from=plugin

## Research gates

1. Re-run with explicitly documented nonzero fees and slippage, chosen from measured exchange costs rather than invented assumptions.
2. Use walk-forward out-of-sample windows and multiple market regimes.
3. Compare against the actual SignalPilot 5m futures logic on a consistent data and execution model.
4. Keep AlgoVault observations in shadow mode and evaluate their incremental value; a confidence score is not a win probability.
5. Never promote historical results into signal verification, risk approval, or demo/live execution.
