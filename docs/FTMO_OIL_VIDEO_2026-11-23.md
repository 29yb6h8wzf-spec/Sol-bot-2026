# YouTube "oil Bollinger breakout" — replication 2026-11-23

Rules from the video transcript: M5 oil, BB(20,2) close-cross + ROC(5) sign; long TP 2.5 % / SL 1.5 %, short TP 1 % / SL 0.5 %. `oil_bb_video.py`.

**The video's own numbers:** monthly results −57, +1.78, −53, −22, +29.69, +29.15 → **sum −71.38** over the 180-day window it shows. The strategy lost money in its own backtest; the "regime" story is chosen after seeing that March/April were good.

**Our replication** on Brent M5 2020-08 → 2023-09 (WTI proxy, FTMO-like costs assumed): 1,410 trades, win rate 34.5 % (video: 34.67 % — rules reproduced faithfully), mean −0.09R/trade. Longs +0.037 %/trade (2021–22 oil bull market), shorts −0.102 %/trade. High-volatility regime (known in advance) −0.026 %/trade — the regime switch does not rescue it. Longest losing streak 15. Half-years: −32.6, +25.4, +12.6, −2.5, −31.0, −20.1 %.
