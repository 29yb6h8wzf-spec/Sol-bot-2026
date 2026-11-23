# Popular "one setup" ideas on H1 — 2026-11-23

`setups_research.py`, 17 FX pairs + XAUUSD, 2007–2023 H1, train ≤2018 / holdout 2019–2023, 2R target, FTMO spreads/commission/swaps.

| Setup | Holdout trades | Holdout R/trade | Win % |
|---|---|---|---|
| Inside-bar breakout | 27,503 | −0.129 | 32% |
| Inside-bar breakout + EMA200 trend | 23,014 | −0.231 | 29% |
| Fair Value Gap pullback + EMA200 trend | 26,415 | −0.075 | 35% |

**Backtest trap found:** the first FVG run showed +0.20R/trade (t = +21). The cause was allowing the target to be hit on the same bar as the limit fill, when the bar's high may have come *before* the fill. Disallowing same-bar targets turned it into −0.075R. Many published FVG/ICT backtests have exactly this lookahead.
