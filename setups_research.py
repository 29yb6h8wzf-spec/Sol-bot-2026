"""Research-only test of popular "one setup" FTMO ideas on H1 (no orders, no network).

  insidebar  mother bar + inside bar; stop order at mother high/low, stop at the
             opposite side, target 2R; optional EMA200 trend filter
  fvg        3-bar fair value gap in EMA200 trend direction; limit entry at the
             gap edge within 12 bars, stop beyond the middle candle, target 2R

Conservative fills: stop-and-target in one bar = stop; limit orders fill only if
price trades through the level. Costs and swaps from h1_research (FTMO spec).
"""
import sys
from pathlib import Path

import numpy as np

import h1_research as h


def _trade(symbol, d, entry, sl, tp, o, hi, lo, c, idx, start, k, days_fn, max_hold=48):
    """Simulate from bar `start` (entry already filled at `entry` on that bar)."""
    entry_eff = entry * (1 + d * k["half_spread"])
    risk = abs(entry - sl)
    end = min(start + max_hold, len(c) - 1)
    exit_px, j = c[end], end
    for j in range(start, end + 1):
        if (lo[j] <= sl) if d > 0 else (hi[j] >= sl):
            exit_px = (min(sl, o[j]) if d > 0 else max(sl, o[j])) * (1 - d * k["slip"]); break
        # On the fill bar we cannot know whether the extreme came before the fill: no target there.
        if j > start and ((hi[j] >= tp) if d > 0 else (lo[j] <= tp)):
            exit_px = tp; break
    exit_px *= (1 - d * k["half_spread"])
    nights = days_fn(start, j)
    if symbol in h.SWAP_POINTS:
        lng, sht, point = h.SWAP_POINTS[symbol]
        swap = -(lng if d > 0 else sht) * point * nights
    else:
        swap = h.SWAP_PER_NIGHT * nights * entry
    pnl = d * (exit_px - entry_eff) - k["fee"] * 2 * entry - swap
    return idx[start], pnl / risk, j


def run_symbol(symbol, df, ind, setup, trend=True, rr=2.0):
    o, hi, lo, c = (df[x].to_numpy() for x in ("Open", "High", "Low", "Close"))
    e200, atr = ind["ema200"].to_numpy(), ind["atr"].to_numpy()
    idx = df.index
    pday = idx.tz_convert("Europe/Prague").normalize()
    days_fn = lambda a, b: max(0, (pday[b] - pday[a]).days)
    k = h.costs(symbol, float(np.nanmean(c)))
    out, i, n = [], 210, len(c)
    while i < n - 2:
        if setup == "insidebar":
            if not (hi[i] < hi[i - 1] and lo[i] > lo[i - 1]):
                i += 1; continue
            mh, ml = hi[i - 1], lo[i - 1]
            if mh - ml < 0.5 * atr[i] or not np.isfinite(atr[i]):
                i += 1; continue
            filled = None
            for j in range(i + 1, min(i + 4, n - 1)):
                up_ok = (not trend) or c[i] > e200[i]
                dn_ok = (not trend) or c[i] < e200[i]
                if up_ok and hi[j] > mh:
                    filled = (1, max(mh, o[j]) * (1 + h.costs(symbol, c[i])["slip"]), ml, j); break
                if dn_ok and lo[j] < ml:
                    filled = (-1, min(ml, o[j]) * (1 - h.costs(symbol, c[i])["slip"]), mh, j); break
            if not filled:
                i += 1; continue
            d, entry, sl, j = filled
        elif setup == "fvg":
            bull = lo[i] > hi[i - 2] and c[i] > e200[i]
            bear = hi[i] < lo[i - 2] and c[i] < e200[i]
            if not (bull or bear) or not np.isfinite(atr[i]):
                i += 1; continue
            d = 1 if bull else -1
            edge = hi[i - 2] if bull else lo[i - 2]
            sl = (lo[i - 1] if bull else hi[i - 1]) - d * 0.1 * atr[i]
            if d * (edge - sl) <= 0.2 * atr[i]:
                i += 1; continue
            j = None
            for m in range(i + 1, min(i + 13, n - 1)):
                if (lo[m] < edge) if bull else (hi[m] > edge):
                    j = m; break
                if (lo[m] <= sl) if bull else (hi[m] >= sl):
                    break
            if j is None:
                i += 1; continue
            entry = min(edge, o[j]) if bull else max(edge, o[j])
        else:
            raise ValueError(setup)
        tp = entry + d * rr * abs(entry - sl)
        t, r, last = _trade(symbol, d, entry, sl, tp, o, hi, lo, c, idx, j, k, days_fn)
        out.append((t, r))
        i = last + 1
    return out


if __name__ == "__main__":
    files = sys.argv[1:]
    data = {}
    for f in files:
        s = Path(f).stem.split("_")[0]
        df = h.load(f)
        data[s] = (df, h.indicators(df))
    for setup, trend in (("insidebar", False), ("insidebar", True), ("fvg", True)):
        tr, ho, per = [], [], {}
        for s, (df, ind) in data.items():
            t = run_symbol(s, df, ind, setup, trend)
            a = [r for ts, r in t if ts < h.TRAIN_END]; b = [r for ts, r in t if ts >= h.TRAIN_END]
            tr += a; ho += b; per[s] = (len(b), float(np.mean(b)) if b else None)
        A, B = np.array(tr), np.array(ho)
        print(f"{setup} trend={trend}: train n={len(A)} R={A.mean():+.3f} win={np.mean(A>0):.2f} | "
              f"holdout n={len(B)} R={B.mean():+.3f} win={np.mean(B>0):.2f} t={B.mean()/B.std()*len(B)**.5:+.2f} | "
              f"EURUSD holdout {per.get('EURUSD')}", flush=True)
