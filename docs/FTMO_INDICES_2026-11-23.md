# Index CFDs (US500, US100, US30, GER40, UK100) — 2026-11-23

D1 2013-05 → 2023-09, `index_research.py`. Costs assumed (spread 0.5–2 pts, long financing 0.015 %/night).

| Hypothesis | 2013–18 mean/trade | 2019–23 mean/trade | Verdict |
|---|---|---|---|
| RSI(2) < 10 dip in uptrend | +0.06 % | +0.08 % (t +0.5) | weak, not significant |
| RSI(2) < 5 dip | +0.35 % | −0.12 % | does not hold |
| Turn of month (last day → 3rd day) | −0.19 % | +0.48 % (t +3.8, all 5 indices +) | flips sign between periods → not reliable without longer history |
| Long while > SMA200 | +0.08 % | +0.91 % | beta of the 2019–23 bull market |

Beta check (1× notional, financing incl.): US100 buy&hold 16.1 %/yr, max DD −35.6 %; with SMA200 filter 10.1 %/yr, −20.9 %. Scaled so the worst historical DD is 8 % (inside FTMO's 10 %): ≈ 4 %/yr → ~2.5 years to a 10 % target. Not viable for a Challenge.
Next check worth doing: turn-of-month on 30+ years of SPY daily data.
