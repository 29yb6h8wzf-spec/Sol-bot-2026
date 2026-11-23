"""Research-only replication of a YouTube "EMA bounce" trend strategy (no orders, no network).

Rules taken from the transcript, made mechanical:
  trend      last two confirmed swing highs AND lows rising (uptrend) / falling (downtrend),
             fractal swings of +-5 bars, confirmed only 5 bars later (no lookahead);
             plus EMA25 above/below EMA50
  impulse    within the last 20 bars price was >= 1 ATR away from EMA25 (no entry on the impulse)
  retrace    bar touches EMA25 (or EMA50) from the trend side
  confirm    rejection candle on that bar: wick toward the EMA >= 50 % of range,
             close back on the trend side of the EMA25 (pin bar)
  fib        (variant) touch within 0.25 ATR of the 50 % level of the last swing leg
  stop       just beyond the bar extreme (0.1 ATR), but at least 2 ATR
  target     last confirmed swing extreme in trend direction; skip if reward < 2R
             (variant: fixed 3R)
  management set and forget; entry next bar open; stop wins same-bar ties; no target on fill bar
Trend lines are not coded (too subjective to replicate). Costs/swaps: FTMO spec via h1_research.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import h1_research as h

K = 5


def swings(hi, lo):
    n = len(hi)
    sh = np.full(n, np.nan); sl = np.full(n, np.nan)
    for i in range(K, n - K):
        if hi[i] == hi[i - K:i + K + 1].max():
            sh[i + K] = hi[i]  # known only at i+K
        if lo[i] == lo[i - K:i + K + 1].min():
            sl[i + K] = lo[i]
    return sh, sl


def run(symbol, df, fib=False, fixed_rr=None):
    o, hi, lo, c = (df[x].to_numpy(float) for x in ("Open", "High", "Low", "Close"))
    s = pd.Series(c)
    e25, e50 = s.ewm(span=25, adjust=False).mean().to_numpy(), s.ewm(span=50, adjust=False).mean().to_numpy()
    tr = np.maximum(hi - lo, np.maximum(abs(hi - np.r_[c[0], c[:-1]]), abs(lo - np.r_[c[0], c[:-1]])))
    atr = pd.Series(tr).rolling(14).mean().to_numpy()
    sh, sl_ = swings(hi, lo)
    k = h.costs(symbol, float(np.nanmean(c)))
    idx = df.index
    pday = idx.tz_convert("Europe/Prague").normalize()
    H, L = [], []
    out, i, n = [], 60, len(c)
    while i < n - 2:
        if np.isfinite(sh[i]): H.append(sh[i])
        if np.isfinite(sl_[i]): L.append(sl_[i])
        a = atr[i]
        if len(H) < 2 or len(L) < 2 or not np.isfinite(a) or a <= 0:
            i += 1; continue
        up = H[-1] > H[-2] and L[-1] > L[-2] and e25[i] > e50[i]
        dn = H[-1] < H[-2] and L[-1] < L[-2] and e25[i] < e50[i]
        d = 1 if up else (-1 if dn else 0)
        if d == 0:
            i += 1; continue
        w = slice(max(0, i - 20), i)
        impulse = (d * (c[w] - e25[w]) >= a).any()
        touch = (lo[i] <= e25[i]) if d > 0 else (hi[i] >= e25[i])
        rng = hi[i] - lo[i]
        wick = (min(o[i], c[i]) - lo[i]) if d > 0 else (hi[i] - max(o[i], c[i]))
        confirm = rng > 0 and wick >= 0.5 * rng and (c[i] > e25[i] if d > 0 else c[i] < e25[i])
        ok = impulse and touch and confirm
        if ok and fib:
            leg_lo, leg_hi = (L[-1], H[-1])
            mid = (leg_lo + leg_hi) / 2
            ok = abs((lo[i] if d > 0 else hi[i]) - mid) <= 0.25 * a
        if not ok:
            i += 1; continue
        e = i + 1
        entry = o[e] * (1 + d * (k["half_spread"] + k["slip"]))
        stop_px = (lo[i] - 0.1 * a) if d > 0 else (hi[i] + 0.1 * a)
        risk = max(d * (entry - stop_px), 2 * a)
        sl = entry - d * risk
        if fixed_rr:
            tp = entry + d * fixed_rr * risk
        else:
            tp = H[-1] if d > 0 else L[-1]
            if d * (tp - entry) < 2 * risk:
                i += 1; continue
        x, j = None, n - 1
        for j in range(e, min(e + 500, n)):
            if (lo[j] <= sl) if d > 0 else (hi[j] >= sl):
                x = (min(sl, o[j]) if d > 0 else max(sl, o[j])) * (1 - d * k["slip"]); break
            if j > e and ((hi[j] >= tp) if d > 0 else (lo[j] <= tp)):
                x = tp; break
        if x is None: x = c[j]
        x *= (1 - d * k["half_spread"])
        nights = max(0, (pday[j] - pday[e]).days)
        if symbol in h.SWAP_POINTS:
            lg, st, pt = h.SWAP_POINTS[symbol]; swap = -(lg if d > 0 else st) * pt * nights
        else:
            swap = h.SWAP_PER_NIGHT * nights * entry
        pnl = d * (x - entry) - k["fee"] * 2 * entry - swap
        out.append((idx[e], pnl / risk))
        for m in range(i + 1, j + 1):  # keep swing lists current while in the trade
            if np.isfinite(sh[m]): H.append(sh[m])
            if np.isfinite(sl_[m]): L.append(sl_[m])
        i = j + 1
    return out


if __name__ == "__main__":
    files = sys.argv[1:]
    data = {Path(f).stem.split("_")[0]: h.load(f) for f in files}
    tf = Path(files[0]).stem.split("_")[1]
    for label, kw in (("swing target, >=2R", {}), ("+ 50% fib confluence", {"fib": True}), ("fixed 3R", {"fixed_rr": 3})):
        allt = [t for s, df in data.items() for t in run(s, df, **kw)]
        r = pd.DataFrame(allt, columns=["t", "R"]).set_index("t").sort_index()
        if len(r) < 2:
            print(f"{label}: {len(r)} trades"); continue
        tr, ho = r[r.index < h.TRAIN_END].R, r[r.index >= h.TRAIN_END].R
        yrs = (r.index[-1] - r.index[0]).days / 365.25
        print(f"{tf} {label:22} n={len(r):6} ({len(r)/yrs/len(data):.0f}/yr/pair) win={np.mean(r.R>0):.2f} "
              f"meanR={r.R.mean():+.3f} | 2007-18 {tr.mean():+.3f} | 2019-23 {ho.mean():+.3f} "
              f"t={ho.mean()/ho.std()*len(ho)**.5:+.1f}", flush=True)
