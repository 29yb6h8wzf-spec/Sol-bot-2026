"""Research-only EURUSD M1 scalping tests with FTMO costs (no orders, no network).

Input: HistData.com MT-format M1 file (BID, timestamps EST without DST = UTC-5).
Hypotheses fixed up front (small grids, reported in full):
  orb_london / orb_ny  first 30 min range of the session; first M1 close outside
                       → enter next open; stop opposite side; target rr×range; flat at cutoff
  fade / follow        5-min move larger than k × mean 5-min abs move (last 2h):
                       fade it or follow it; stop = move size, target = half move; max 15 min
Costs per round trip: FTMO raw spread 0.09 pip (ASK = BID + spread), commission
$5/lot = 0.5 pip, slippage 0.1 pip on market fills (entries, stops, time exits).
Same-bar rule: no target on the entry bar; stop-and-target in one bar = stop.
"""
import sys

import numpy as np
import pandas as pd

PIP = 0.0001
SPREAD, COMM, SLIP = 0.09, 0.5, 0.1  # pips


def load_histdata(path):
    df = pd.read_csv(path, header=None, names=["d", "t", "o", "h", "l", "c", "v"])
    ts = pd.to_datetime(df["d"] + " " + df["t"], format="%Y.%m.%d %H:%M") + pd.Timedelta(hours=5)
    df.index = ts.dt.tz_localize("UTC")
    return df[["o", "h", "l", "c"]].astype(float)


def _exit(d, entry, sl, tp, o, h, l, c, start, last):
    """Return (exit_price_bid_side_raw, j, market_exit) for a long(d=1)/short(d=-1)."""
    for j in range(start, last + 1):
        if (l[j] <= sl) if d > 0 else (h[j] >= sl):
            return (min(sl, o[j]) if d > 0 else max(sl, o[j])), j, True
        if j > start and ((h[j] >= tp) if d > 0 else (l[j] <= tp)):
            return tp, j, False
    return c[last], last, True


def pnl_pips(d, entry_mid, exit_mid, market_exit):
    gross = d * (exit_mid - entry_mid) / PIP
    cost = SPREAD + COMM + SLIP + (SLIP if market_exit else 0)
    return gross, gross - cost


def orb(df, start_h, start_m, cutoff_h, rr):
    o, h, l, c = (df[x].to_numpy() for x in "ohlc")
    idx = df.index
    out = []
    for day, g in df.groupby(idx.date):
        gi = np.flatnonzero((idx.date == day))
        mins = idx[gi].hour * 60 + idx[gi].minute
        s = start_h * 60 + start_m
        rng = gi[(mins >= s) & (mins < s + 30)]
        after = gi[(mins >= s + 30) & (mins < cutoff_h * 60)]
        if len(rng) < 20 or len(after) < 10:
            continue
        hi, lo = h[rng].max(), l[rng].min()
        if (hi - lo) / PIP < 3:
            continue
        for k, i in enumerate(after[:-1]):
            d = 1 if c[i] > hi else (-1 if c[i] < lo else 0)
            if d:
                e = i + 1
                entry = o[e]
                sl = lo if d > 0 else hi
                tp = entry + d * rr * (hi - lo)
                x, j, mkt = _exit(d, entry, sl, tp, o, h, l, c, e, after[-1])
                out.append((idx[e], *pnl_pips(d, entry, x, mkt)))
                break
    return out


def move(df, k, follow):
    o, h, l, c = (df[x].to_numpy() for x in "ohlc")
    idx = df.index
    m5 = pd.Series(c, index=idx).diff(5)
    scale = m5.abs().rolling(120).mean().to_numpy()
    m5 = m5.to_numpy()
    gap = np.r_[False, np.diff(idx.asi8) > 60_000_000_000 * 5]
    out, i, n = [], 130, len(c)
    while i < n - 20:
        if not np.isfinite(scale[i]) or gap[i - 5:i + 1].any() or abs(m5[i]) < k * scale[i] or abs(m5[i]) / PIP < 2:
            i += 1
            continue
        d = int(np.sign(m5[i])) * (1 if follow else -1)
        e = i + 1
        size = abs(m5[i])
        entry = o[e]
        sl, tp = entry - d * size, entry + d * size / 2
        x, j, mkt = _exit(d, entry, sl, tp, o, h, l, c, e, min(e + 15, n - 1))
        out.append((idx[e], *pnl_pips(d, entry, x, mkt)))
        i = j + 1
    return out


def report(name, trades):
    if not trades:
        print(f"{name:32} no trades"); return
    t = pd.DataFrame(trades, columns=["t", "gross", "net"]).set_index("t")
    days = t.index.normalize().nunique()
    h1, h2 = t[t.index.month <= 6], t[t.index.month > 6]
    tstat = t.net.mean() / t.net.std() * len(t) ** .5
    print(f"{name:32} n={len(t):6} /day={len(t)/max(days,1):5.1f} gross={t.gross.mean():+.2f}p "
          f"net={t.net.mean():+.2f}p t={tstat:+.1f} win={np.mean(t.net>0):.2f} | "
          f"H1 net={h1.net.mean():+.2f}p H2 net={h2.net.mean():+.2f}p", flush=True)
    return t


if __name__ == "__main__":
    df = load_histdata(sys.argv[1])
    print("bars", len(df), df.index[0], df.index[-1])
    for rr in (1.0, 2.0):
        report(f"orb_london 07:00 rr={rr}", orb(df, 7, 0, 11, rr))
        report(f"orb_ny 13:30 rr={rr}", orb(df, 13, 30, 17, rr))
    for k in (2.0, 3.0, 4.0):
        report(f"fade k={k}", move(df, k, follow=False))
        report(f"follow k={k}", move(df, k, follow=True))
