"""Research-only: S&P 500 turn-of-month (TOM) edge and FTMO Challenge simulation (no orders).

Data: github.com/SteelCerberus/us-market-data (daily S&P 500 close, Yahoo-based; unverified).
TOM: long at the close of the last trading day of the month, exit at the close of the 3rd
trading day of the new month. Optional filter: only if close > SMA200 at entry.
CFD costs (assumed): 0.02 % round trip + 0.015 % financing per calendar night.
FTMO 2-Step simulation on daily closes (intraday swings not modelled): daily -5 % from
previous close equity, static -10 %, target +10 %, starting every month 1990-2023.
"""
import sys
import numpy as np
import pandas as pd

d = pd.read_csv(sys.argv[1], parse_dates=["Date"]).set_index("Date")
c_all = d["Close"]
sma = c_all.rolling(200).mean()
c = c_all[c_all.index >= "1990-01-01"]; sma = sma.reindex(c.index)
dr = c.pct_change().fillna(0).to_numpy()
m = c.index.to_period("M"); last = np.flatnonzero(np.r_[m[1:] != m[:-1], False])


def series(use_filter):
    inpos = np.zeros(len(c), bool); cost = np.zeros(len(c)); trades = []
    for p in last:
        if p + 3 >= len(c) or (use_filter and c.iloc[p] < sma.iloc[p]):
            continue
        inpos[p + 1:p + 4] = True
        cost[p + 3] += 0.0002 + 0.00015 * (c.index[p + 3] - c.index[p]).days
        trades.append(c.iloc[p + 3] / c.iloc[p] - 1 - cost[p + 3])
    return np.where(inpos, dr, 0) - cost, np.array(trades)


def challenge(strat, L, horizon_m=24):
    res = {"pass": 0, "fail_daily": 0, "fail_total": 0, "timeout": 0}; mos = []
    for s in [p + 1 for p in last][:-30]:
        eq, out = 0.0, "timeout"
        for k in range(s, min(s + 21 * horizon_m, len(c))):
            start = eq; eq += L * strat[k]
            if eq <= start - 0.05: out = "fail_daily"; break
            if eq <= -0.10: out = "fail_total"; break
            if eq >= 0.10: out = "pass"; mos.append((k - s) / 21); break
        res[out] += 1
    n = sum(res.values())
    return {k: round(v / n, 2) for k, v in res.items()}, (round(float(np.median(mos)), 1) if mos else None)


for f in (False, True):
    s, t = series(f)
    print(f"filter SMA200={f}: trades={len(t)} ({len(t)/35:.1f}/yr) mean net={t.mean()*100:+.3f}% win={np.mean(t>0):.2f} worst={t.min()*100:.1f}%")
    for L in (1, 1.5, 2, 3):
        r, med = challenge(s, L)
        print(f"   x{L}: {r} median months to pass={med}")
