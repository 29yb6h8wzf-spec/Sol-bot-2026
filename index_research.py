"""Research-only index CFD scan for FTMO (no orders, no network).

Hypotheses with an economic reason (equity indices have positive drift; dips get bought;
month-turn pension/payroll flows), tested on 5 index CFDs 2013-2023 (D1, UTC):
  dip       close > SMA200 and RSI(2) < th -> long next open; exit close > SMA5 or 10 days;
            catastrophic stop 3 ATR(14)
  tom       turn of month: long at close of last trading day, exit close of 3rd trading day
  trend     baseline beta: long while close > SMA200
Costs (ASSUMED, verify with FTMO symbol spec): spread below, slippage = half spread per fill,
long financing 0.015 % of notional per night (Fri->Mon counts 3).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SPREAD_PTS = {"USA500IDXUSD": 0.5, "USATECHIDXUSD": 1.5, "USA30IDXUSD": 2.0, "DEUIDXEUR": 1.5, "GBRIDXGBP": 1.0}
SWAP_NIGHT = 0.00015
SPLIT = pd.Timestamp("2019-01-01")


def load(p):
    df = pd.read_csv(p, sep="\t", parse_dates=["Time"]).set_index("Time")
    df = df[df.index.dayofweek < 5]
    return df[["Open", "High", "Low", "Close"]].astype(float)


def trades(sym, df, kind, th=10):
    o, h, l, c = (df[x].to_numpy() for x in ("Open", "High", "Low", "Close"))
    s = df["Close"]
    sma200, sma5 = s.rolling(200).mean().to_numpy(), s.rolling(5).mean().to_numpy()
    d = s.diff()
    up, dn = d.clip(lower=0).ewm(alpha=.5, adjust=False).mean(), (-d.clip(upper=0)).ewm(alpha=.5, adjust=False).mean()
    rsi = (100 - 100 / (1 + up / dn)).to_numpy()
    tr = np.maximum(h - l, np.maximum(abs(h - np.r_[c[0], c[:-1]]), abs(l - np.r_[c[0], c[:-1]])))
    atr = pd.Series(tr).rolling(14).mean().to_numpy()
    cost = SPREAD_PTS[sym] * 1.0  # half spread + slippage each side ~ one spread per side
    idx = df.index
    month = idx.month
    out, i, n = [], 201, len(c)
    while i < n - 2:
        if kind == "dip":
            go = c[i] > sma200[i] and rsi[i] < th
        elif kind == "tom":
            go = month[i + 1] != month[i]
        elif kind == "trend":
            go = c[i] > sma200[i]
        if not go:
            i += 1; continue
        e = i + 1
        entry = o[e] + cost / 2 if kind != "tom" else c[i] + cost / 2
        start = e if kind != "tom" else i
        stop = entry - 3 * atr[i]
        x, j = None, n - 1
        for j in range(e, n):
            if l[j] <= stop:
                x = min(stop, o[j]) - cost / 2; break
            if kind == "dip" and (c[j] > sma5[j] or j - e >= 9):
                x = c[j] - cost / 2; break
            if kind == "tom" and sum(month[i + 1:j + 1] == month[i + 1]) >= 3:
                x = c[j] - cost / 2; break
            if kind == "trend" and c[j] < sma200[j]:
                x = c[j] - cost / 2; break
        if x is None:
            x = c[j]
        nights = (idx[j] - idx[start]).days
        ret = (x - entry) / entry - SWAP_NIGHT * nights
        gross = (x - entry + cost) / entry
        out.append((idx[start], ret, gross, nights))
        i = j + 1
    return out


def report(name, rows):
    t = pd.DataFrame(rows, columns=["t", "ret", "gross", "nights"]).set_index("t").sort_index()
    a, b = t[t.index < SPLIT], t[t.index >= SPLIT]
    yrs = lambda x: max((x.index[-1] - x.index[0]).days / 365.25, .5) if len(x) else 1
    tt = b.ret.mean() / b.ret.std() * len(b) ** .5 if len(b) > 2 else float("nan")
    print(f"{name:28} n={len(t):4} win={np.mean(t.ret>0):.2f} | 2013-18 mean={a.ret.mean()*100:+.3f}% "
          f"({a.ret.sum()/yrs(a)*100:+.1f}%/yr) | 2019-23 mean={b.ret.mean()*100:+.3f}% gross={b.gross.mean()*100:+.3f}% "
          f"({b.ret.sum()/yrs(b)*100:+.1f}%/yr) t={tt:+.1f} | worst trade {t.ret.min()*100:.1f}%", flush=True)


if __name__ == "__main__":
    data = {Path(f).stem.split("_")[0]: load(f) for f in sys.argv[1:]}
    for kind, kw in (("dip", {"th": 10}), ("dip", {"th": 5}), ("tom", {}), ("trend", {})):
        allrows = []
        for s, df in data.items():
            r = trades(s, df, kind, **kw)
            allrows += r
            report(f"  {s} {kind}{kw.get('th','')}", r)
        report(f"POOLED {kind}{kw.get('th','')}", allrows)
