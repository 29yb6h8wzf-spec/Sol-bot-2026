"""Research-only replication of a YouTube 'oil Bollinger breakout' strategy (no orders).

Rules as stated in the video (USOIL M5): BB(20,2).
  Long : close crosses above upper band AND ROC(5) > 0 -> buy, TP +2.5 %, SL -1.5 %
  Short: close crosses below lower band AND ROC(5) < 0 -> sell, TP -1 %,  SL +0.5 %
Entry next bar open, one position at a time, stop wins if both hit in one bar,
no target on the fill bar. Data: Brent M5 as a WTI proxy (unverified source).
Costs (assumed): spread $0.03, slippage $0.01 per market fill, commission 0.001 %/side.
"""
import sys
import numpy as np
import pandas as pd

SPREAD, SLIP, COMM = 0.03, 0.01, 0.00001

df = pd.read_csv(sys.argv[1], sep="\t", parse_dates=["Time"]).set_index("Time")
o, h, l, c = (df[x].to_numpy(float) for x in ("Open", "High", "Low", "Close"))
s = pd.Series(c)
mid, sd = s.rolling(20).mean(), s.rolling(20).std(ddof=0)
up, lo = (mid + 2 * sd).to_numpy(), (mid - 2 * sd).to_numpy()
roc = (s / s.shift(5) - 1).to_numpy()
idx = df.index
# volatility regime known at the time: 20-day realized range vs its trailing 250-day median
day = df["Close"].resample("1D").last().dropna()
dvol = day.pct_change().abs().rolling(20).mean()
hot = (dvol > dvol.rolling(250, min_periods=60).median()).shift(1).reindex(idx, method="ffill").fillna(False).to_numpy()

trades, i, n = [], 21, len(c)
while i < n - 2:
    d = 0
    if c[i] > up[i] and c[i - 1] <= up[i - 1] and roc[i] > 0: d, tpp, slp = 1, .025, .015
    elif c[i] < lo[i] and c[i - 1] >= lo[i - 1] and roc[i] < 0: d, tpp, slp = -1, .01, .005
    if d == 0:
        i += 1; continue
    e = i + 1
    entry = o[e] + d * (SPREAD / 2 + SLIP)
    tp, sl = entry * (1 + d * tpp), entry * (1 - d * slp)
    x, j = None, n - 1
    for j in range(e, n):
        if (l[j] <= sl) if d > 0 else (h[j] >= sl):
            x = (min(sl, o[j]) if d > 0 else max(sl, o[j])) - d * SLIP; break
        if j > e and ((h[j] >= tp) if d > 0 else (l[j] <= tp)):
            x = tp; break
    if x is None: x = c[j]
    x -= d * SPREAD / 2
    ret = d * (x - entry) / entry - 2 * COMM
    trades.append((idx[e], d, ret, ret / slp, hot[i], (idx[j] - idx[e]).total_seconds() / 3600))
    i = j + 1

t = pd.DataFrame(trades, columns=["t", "side", "ret", "R", "hot", "hours"]).set_index("t")
print(f"data {idx[0]} -> {idx[-1]}  trades={len(t)}  per day={len(t)/idx.normalize().nunique():.1f}")
print(f"win={np.mean(t.ret>0):.3f} meanR={t.R.mean():+.3f} mean ret={t.ret.mean()*100:+.3f}%  median hold={t.hours.median():.1f}h")
for side, g in t.groupby("side"):
    print(f"  {'long ' if side>0 else 'short'} n={len(g)} win={np.mean(g.ret>0):.3f} mean ret={g.ret.mean()*100:+.3f}%")
for k, g in t.groupby("hot"):
    print(f"  regime {'HIGH vol' if k else 'low vol '} n={len(g)} mean ret={g.ret.mean()*100:+.3f}%")
eq = (1 + t.ret * 0.5).cumprod()  # 0.5x notional for a rough curve
print("by half-year sum ret %:", (t.ret.groupby(pd.Grouper(freq="6MS")).sum() * 100).round(1).to_dict())
lose = (t.ret <= 0).astype(int); streak = (lose.groupby((lose != lose.shift()).cumsum()).cumsum()).max()
print("longest losing streak", streak)
