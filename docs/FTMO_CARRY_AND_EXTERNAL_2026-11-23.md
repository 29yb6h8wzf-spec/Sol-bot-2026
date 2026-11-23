# JPY carry + trend, and an external GitHub bot — 2026-11-23

**Carry + trend (daily, 2007–2023):** long USDJPY/EURJPY/GBPJPY when close > EMA200, flat otherwise, 1× notional, FTMO swap points (today's values applied historically), spread/commission/slippage on each switch.

| Pair | CAGR | Max DD | Swap income/yr at FTMO rates |
|---|---|---|---|
| USDJPY | +1.7 % | −25.1 % | +0.9 % |
| EURJPY | −0.1 % | −32.9 % | +0.5 % |
| GBPJPY | +1.5 % | −27.6 % | +1.5 % |

FTMO swaps are too small to carry the strategy, and drawdowns are 2.5–3× the 10 % Max Loss. Not usable.

**github.com/Dahshan228/FTMO-TradingBot** (recommended in a pasted article): its own README reports +7.8 %/yr estimated live, max DD 13.5 % (> FTMO 10 % Max Loss), and a probability of backtest overfitting of 0.588 for the equity model. Forex leg = golden cross on JPY crosses (the carry trade above). Not Challenge-grade by its author's own numbers.
