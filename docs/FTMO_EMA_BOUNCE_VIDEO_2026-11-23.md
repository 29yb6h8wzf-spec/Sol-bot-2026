# YouTube "EMA bounce" trend strategy — replication 2026-11-23

Rules from the transcript, made mechanical in `ema_bounce.py`: swing-structure trend (HH/HL or LH/LL, fractal ±5, no lookahead) + EMA25/50 alignment, impulse away from EMA25 then pullback touch, pin-bar rejection, stop beyond the bar but ≥ 2 ATR, target at last swing with ≥ 2R required (or fixed 3R), set-and-forget. Trend lines not coded. FTMO spreads/commission/swaps. 17 FX pairs (+ XAUUSD on H1), 2007–2023.

| TF | Variant | Trades | Win | Mean R | 2007–18 | 2019–23 | t (19–23) |
|---|---|---|---|---|---|---|---|
| H1 | swing target ≥ 2R | 601 | 27 % | −0.118 | −0.052 | −0.268 | −2.5 |
| H1 | + 50 % fib | 19 | 37 % | +0.164 | — | — | +0.4 (too few) |
| H1 | fixed 3R | 14,775 | 24 % | −0.077 | −0.081 | −0.069 | −2.7 |
| H4 | swing target ≥ 2R | 54 | 48 % | +0.578 | +0.941 | −0.147 | −0.4 (too few) |
| H4 | fixed 3R | 3,677 | 25 % | −0.059 | −0.033 | −0.120 | −2.4 |

Requiring "≥ 2 ATR stop" and "≥ 2R to the last swing" together leaves almost no trades; when it is made tradable (fixed 3R) it loses consistently.
