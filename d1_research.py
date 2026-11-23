"""Research-only daily-timeframe FX scan + FTMO Challenge Monte Carlo (no orders, no network).

Families (classic, low-parameter):
  tsmom     weekly rebalance, side = sign of N-day return; catastrophic stop 3 ATR
  turtle    break of N-day high/low, 2 ATR stop, exit on N/2-day opposite break
  macross   EMA50/EMA200 cross, 3 ATR stop, exit on opposite cross
Signals on daily close, entry next day open. Costs from h1_research (assumed).

FTMO simulation: each trade risks a fixed fraction of INITIAL capital; open
trades are marked to market at each daily close (intraday swings are NOT
modelled, so true breach rates are somewhat higher). Challenge paths start on
every historical day of the evaluated period and use the real sequence.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from h1_research import SWAP_PER_NIGHT, costs, load

TRAIN_END = pd.Timestamp("2019-01-01", tz="UTC")


def prep(df):
    df = df[df.index.dayofweek < 5].copy()  # drop Sunday stubs
    c = df["Close"]
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - c.shift()).abs(), (df["Low"] - c.shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(20).mean()
    df["ema50"], df["ema200"] = c.ewm(span=50, adjust=False).mean(), c.ewm(span=200, adjust=False).mean()
    return df


def trades_for(symbol, df, cfg):
    o, h, l, c, atr = (df[x].to_numpy() for x in ("Open", "High", "Low", "Close", "atr"))
    idx = df.index
    n = len(c)
    k = costs(symbol, float(np.nanmean(c)))
    fam = cfg["family"]
    N = cfg.get("n", 0)
    hi = pd.Series(h).rolling(N).max().shift().to_numpy() if fam == "turtle" else None
    lo = pd.Series(l).rolling(N).min().shift().to_numpy() if fam == "turtle" else None
    hx = pd.Series(h).rolling(max(N // 2, 1)).max().shift().to_numpy() if fam == "turtle" else None
    lx = pd.Series(l).rolling(max(N // 2, 1)).min().shift().to_numpy() if fam == "turtle" else None
    e50, e200 = df["ema50"].to_numpy(), df["ema200"].to_numpy()
    monday = idx.dayofweek.to_numpy() == 0

    def want(i):
        if not np.isfinite(atr[i]) or i < 210:
            return 0
        if fam == "tsmom":
            return 0 if not monday[i] else int(np.sign(c[i] / c[i - N] - 1))
        if fam == "turtle":
            return 1 if c[i] > hi[i] else (-1 if c[i] < lo[i] else 0)
        if fam == "macross":
            up, prev = e50[i] > e200[i], e50[i - 1] > e200[i - 1]
            return (1 if up else -1) if up != prev else 0
        raise ValueError(fam)

    out = []
    i = 210
    while i < n - 1:
        d = want(i)
        if d == 0:
            i += 1
            continue
        e = i + 1
        mult = 2 if fam == "turtle" else 3
        entry = o[e] * (1 + d * (k["half_spread"] + k["slip"]))
        risk_px = mult * atr[i]
        sl = entry - d * risk_px
        path = []  # daily mark-to-market R at each close while open
        exit_px, j = None, e
        for j in range(e, n):
            if (l[j] <= sl) if d > 0 else (h[j] >= sl):
                exit_px = (min(sl, o[j]) if d > 0 else max(sl, o[j])) * (1 - d * k["slip"])
                break
            flip = False
            if fam == "tsmom" and monday[j] and j > e:
                flip = int(np.sign(c[j] / c[j - N] - 1)) != d
            elif fam == "turtle":
                flip = (c[j] < lx[j]) if d > 0 else (c[j] > hx[j])
            elif fam == "macross":
                flip = (e50[j] > e200[j]) != (d > 0)
            if flip or j == n - 1:
                exit_px = c[j] * (1 - d * k["slip"])
                break
            path.append(d * (c[j] - entry) / risk_px)
        exit_px *= (1 - d * k["half_spread"])
        days = (idx[j] - idx[e]).days
        cost_r = (k["fee"] * 2 * entry + SWAP_PER_NIGHT * days * entry) / risk_px
        final_r = d * (exit_px - entry) / risk_px - cost_r
        path.append(final_r)
        out.append({"sym": symbol, "entry_t": idx[e], "exit_t": idx[j], "r": final_r,
                    "path_t": list(idx[e:e + len(path)]), "path_r": path})
        i = j + 1 if fam != "turtle" else j
    return out


GRID = ([{"family": "tsmom", "n": n} for n in (20, 60, 120, 250)]
        + [{"family": "turtle", "n": n} for n in (20, 55, 100)]
        + [{"family": "macross"}])


def daily_portfolio_r(trades, start, end):
    """Sum of daily changes in mark-to-market R across all open trades."""
    days = pd.bdate_range(start, end, tz="UTC")
    s = pd.Series(0.0, index=days)
    for t in trades:
        prev = 0.0
        for ts, r in zip(t["path_t"], t["path_r"]):
            ts = ts.normalize()
            if start <= ts <= end and ts in s.index:
                s[ts] += r - prev
            prev = r
    return s


def challenge(daily_r, risk, plan="two_step", horizon=250):
    """Fraction of start days that pass / breach / time out. Equity in % of ISC."""
    x = daily_r.to_numpy() * risk
    n = len(x)
    res = {"pass": 0, "fail_daily": 0, "fail_total": 0, "timeout": 0}
    days_to_pass = []
    dl = 0.05 if plan == "two_step" else 0.03
    for s in range(0, max(n - 20, 1)):
        eq, peak_eod, best, total_pos = 0.0, 0.0, 0.0, []
        outcome = "timeout"
        for k in range(s, min(s + horizon, n)):
            day_start = eq
            eq += x[k]
            if eq <= day_start - dl:
                outcome = "fail_daily"; break
            floor = -0.10 if plan == "two_step" else peak_eod - 0.10
            if eq <= floor:
                outcome = "fail_total"; break
            peak_eod = max(peak_eod, eq)
            total_pos.append(x[k])
            if eq >= 0.10:
                if plan == "one_step":
                    if max(total_pos) > 0.5 * sum(total_pos):
                        continue
                outcome = "pass"; days_to_pass.append(k - s + 1); break
        res[outcome] += 1
    tot = sum(res.values())
    out = {k: round(v / tot, 3) for k, v in res.items()}
    out["median_days_to_pass"] = int(np.median(days_to_pass)) if days_to_pass else None
    return out


if __name__ == "__main__":
    out_path, files = sys.argv[1], sys.argv[2:]
    data = {Path(p).stem.split("_")[0]: prep(load(p)) for p in files}
    rows = []
    best = None
    for cfg in GRID:
        allt = [t for s, df in data.items() for t in trades_for(s, df, cfg)]
        tr = [t["r"] for t in allt if t["entry_t"] < TRAIN_END]
        ho = [t["r"] for t in allt if t["entry_t"] >= TRAIN_END]
        row = {"cfg": cfg, "train": {"n": len(tr), "meanR": float(np.mean(tr))},
               "holdout": {"n": len(ho), "meanR": float(np.mean(ho))}}
        rows.append(row)
        print(cfg, row["train"], row["holdout"], flush=True)
        if best is None or row["train"]["meanR"] > best[0]["train"]["meanR"]:
            best = (row, allt)
    row, allt = best
    first = min(df.index[0] for df in data.values())
    last = max(df.index[-1] for df in data.values())
    ho_daily = daily_portfolio_r([t for t in allt if t["entry_t"] >= TRAIN_END], TRAIN_END, last)
    tr_daily = daily_portfolio_r([t for t in allt if t["entry_t"] < TRAIN_END], first.normalize(), TRAIN_END)
    mc = {}
    for risk in (0.0025, 0.005, 0.01, 0.02, 0.03):
        mc[str(risk)] = {"holdout_two_step": challenge(ho_daily, risk), "holdout_one_step": challenge(ho_daily, risk, "one_step"),
                         "train_two_step": challenge(tr_daily, risk)}
        print(risk, mc[str(risk)], flush=True)
    Path(out_path).write_text(json.dumps({"status": "OFFLINE_RESEARCH_ONLY", "orders_sent": False, "rows": rows,
                                          "selected_on_train": row["cfg"], "ftmo_monte_carlo": mc,
                                          "holdout_daily_r_sum": float(ho_daily.sum()),
                                          "holdout_worst_day_r": float(ho_daily.min())}, default=str, indent=1))
