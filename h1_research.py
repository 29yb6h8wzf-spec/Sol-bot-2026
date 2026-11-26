"""Research-only H1 forex strategy scan for FTMO (no orders, no network).

Hypothesis: on H1 with multi-hour/multi-day holds, costs are a small share of
the move, unlike 5m scalps. Four classic, low-parameter families:

  donchian   breakout of the N-bar high/low, ATR stop/target
  pullback   EMA50>EMA200 trend, close reclaims EMA20, ATR stop/target
  london     break of the 00:00-07:00 UTC range between 07:00-11:00 UTC, flat at 20:00
  rsi2       Connors-style RSI(2) dip in an EMA200 trend, exit on close > EMA5

Signals use bar-close data; entries at next bar open. If stop and target are
both inside one bar, the stop is assumed (conservative). Results are in R
(multiples of initial risk) after spread, commission, slippage and swap.
Cost numbers are ASSUMPTIONS until checked against FTMO's MT5 symbol specs.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

TRAIN_END = pd.Timestamp("2019-01-01", tz="UTC")
BASE_USD = {"EUR": 1.15, "GBP": 1.3, "AUD": 0.72, "NZD": 0.66, "USD": 1.0, "CAD": 0.76, "CHF": 1.05}
SPREAD_PIPS = {"XAUUSD": 20}
DEFAULT_SPREAD = 1.0
COMMISSION_RT_PER_LOT = 5.0
SLIP_PIPS = 0.1
SWAP_PER_NIGHT = 0.00007
# FTMO symbol specs supplied by the user 2026-11-23 (avg raw spread, swap points).
_SPEC_PATH = Path(__file__).with_name("research_inputs") / "ftmo_forex_specs_2026-11-23.json"
SWAP_POINTS = {}
if _SPEC_PATH.exists():
    for _sym, _s in json.loads(_SPEC_PATH.read_text()).items():
        if _s.get("spread_pips") is not None:
            SPREAD_PIPS[_sym] = float(_s["spread_pips"])
        if _s.get("swap_long") is not None and _s.get("swap_short") is not None:
            SWAP_POINTS[_sym] = (float(_s["swap_long"]), float(_s["swap_short"]), float(_s["point"]))


def costs(symbol, price):
    pip = 0.01 if ("JPY" in symbol or symbol == "XAUUSD") else 0.0001
    spread = SPREAD_PIPS.get(symbol, DEFAULT_SPREAD) * pip / price
    slip = SLIP_PIPS * pip / price
    if symbol == "XAUUSD":
        fee = 0.000014
    else:
        fee = COMMISSION_RT_PER_LOT / 2 / (100000 * BASE_USD[symbol[:3]])
    return {"half_spread": spread / 2, "slip": slip, "fee": fee}


def load(path):
    df = pd.read_csv(path, sep=None, engine="python")
    df.columns = [c.strip().capitalize() for c in df.columns]
    df["Time"] = pd.to_datetime(df["Time"], utc=True)
    return df.set_index("Time")[["Open", "High", "Low", "Close"]].astype(float)


def indicators(df):
    c = df["Close"]
    out = pd.DataFrame(index=df.index)
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - c.shift()).abs(), (df["Low"] - c.shift()).abs()], axis=1).max(axis=1)
    out["atr"] = tr.rolling(24).mean()
    for n in (5, 20, 50, 200):
        out[f"ema{n}"] = c.ewm(span=n, adjust=False).mean()
    d = c.diff()
    up, dn = d.clip(lower=0).ewm(alpha=0.5, adjust=False).mean(), (-d.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    out["rsi2"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    for n in (48, 120, 240):
        out[f"hi{n}"] = df["High"].rolling(n).max().shift()
        out[f"lo{n}"] = df["Low"].rolling(n).min().shift()
    hour = df.index.hour
    day = df.index.floor("D")
    asia = (hour < 7)
    rng_hi = df["High"].where(asia).groupby(day).cummax()
    rng_lo = df["Low"].where(asia).groupby(day).cummin()
    out["asia_hi"] = rng_hi.groupby(day).transform("max")
    out["asia_lo"] = rng_lo.groupby(day).transform("min")
    out["asia_complete"] = pd.Series(asia, index=df.index).groupby(day).transform("sum") >= 6
    return out


def signals(df, ind, cfg):
    """Return arrays: direction (+1/-1/0) on signal bar, stop distance, target distance (nan = none)."""
    c, atr = df["Close"].to_numpy(), ind["atr"].to_numpy()
    n = len(c)
    direction = np.zeros(n)
    stop = np.full(n, np.nan)
    target = np.full(n, np.nan)
    fam = cfg["family"]
    if fam == "donchian":
        hi, lo = ind[f"hi{cfg['n']}"].to_numpy(), ind[f"lo{cfg['n']}"].to_numpy()
        prev_c = np.roll(c, 1)
        direction[(c > hi) & (prev_c <= np.roll(hi, 1))] = 1
        direction[(c < lo) & (prev_c >= np.roll(lo, 1))] = -1
        stop[:] = cfg["k"] * atr
        target[:] = cfg["r"] * atr
    elif fam == "pullback":
        e20, e50, e200 = (ind[f"ema{x}"].to_numpy() for x in (20, 50, 200))
        prev_c, prev_e20 = np.roll(c, 1), np.roll(e20, 1)
        direction[(e50 > e200) & (prev_c < prev_e20) & (c > e20)] = 1
        direction[(e50 < e200) & (prev_c > prev_e20) & (c < e20)] = -1
        stop[:] = cfg["k"] * atr
        target[:] = cfg["r"] * atr
    elif fam == "london":
        hour = df.index.hour.to_numpy()
        ahi, alo = ind["asia_hi"].to_numpy(), ind["asia_lo"].to_numpy()
        ok = ind["asia_complete"].to_numpy() & (hour >= 7) & (hour < 11)
        width = ahi - alo
        ok &= (width > 0.3 * atr) & (width < 3 * atr)
        direction[ok & (c > ahi)] = 1
        direction[ok & (c < alo)] = -1
        sd = np.where(direction > 0, c - (alo if cfg["stop"] == "far" else (ahi + alo) / 2),
                      (ahi if cfg["stop"] == "far" else (ahi + alo) / 2) - c)
        stop[:] = sd
        target[:] = cfg["r"] * sd
    elif fam == "rsi2":
        rsi, e200 = ind["rsi2"].to_numpy(), ind["ema200"].to_numpy()
        direction[(rsi < cfg["lo"]) & (c > e200)] = 1
        direction[(rsi > 100 - cfg["lo"]) & (c < e200)] = -1
        stop[:] = 3 * atr
    direction[~np.isfinite(stop) | (stop <= 0)] = 0
    return direction, stop, target


def simulate(symbol, df, ind, cfg):
    direction, stop_d, target_d = signals(df, ind, cfg)
    o, h, l, c = (df[x].to_numpy() for x in ("Open", "High", "Low", "Close"))
    idx = df.index
    hours = idx.hour.to_numpy()
    prague_day = idx.tz_convert("Europe/Prague").normalize()
    e5 = ind["ema5"].to_numpy()
    price = float(np.nanmean(c))
    k = costs(symbol, price)
    hold = cfg.get("hold", 240)
    trades = []
    i, n = 1, len(c)
    while i < n - 1:
        d = direction[i]
        if d == 0:
            i += 1
            continue
        e_i = i + 1
        entry = o[e_i] * (1 + d * (k["half_spread"] + k["slip"]))
        sl = entry - d * stop_d[i]
        tp = entry + d * target_d[i] if np.isfinite(target_d[i]) else np.nan
        exit_px, j, reason = None, e_i, "TIME"
        last = min(e_i + hold, n - 1)
        for j in range(e_i, last + 1):
            if (idx[j] - idx[j - 1]).total_seconds() > 4 * 86400:
                pass  # long gap: stop/target checks below still use the new bar's open
            hit_sl = l[j] <= sl if d > 0 else h[j] >= sl
            hit_tp = np.isfinite(tp) and (h[j] >= tp if d > 0 else l[j] <= tp)
            if hit_sl:
                exit_px = (min(sl, o[j]) if d > 0 else max(sl, o[j])) * (1 - d * k["slip"])
                reason = "STOP"
                break
            if hit_tp:
                exit_px, reason = tp, "TARGET"
                break
            if cfg["family"] == "london" and hours[j] >= 20:
                exit_px, reason = c[j] * (1 - d * k["slip"]), "EOD"
                break
            if cfg["family"] == "rsi2" and (c[j] > e5[j] if d > 0 else c[j] < e5[j]):
                exit_px, reason = c[j] * (1 - d * k["slip"]), "SIGNAL"
                break
        if exit_px is None:
            j = last
            exit_px = c[j] * (1 - d * k["slip"])
        exit_px *= (1 - d * k["half_spread"])
        nights = max(0, (prague_day[j] - prague_day[e_i]).days)
        if symbol in SWAP_POINTS:
            lng, sht, point = SWAP_POINTS[symbol]
            swap = -(lng if d > 0 else sht) * point * nights / entry
        else:
            swap = SWAP_PER_NIGHT * nights
        ret = d * (exit_px - entry) / entry - k["fee"] * 2 - swap
        risk = stop_d[i] / entry
        trades.append((idx[i], ret / risk, reason))
        i = j + 1
    return trades


GRID = (
    [{"family": "donchian", "n": n, "k": k, "r": r} for n in (48, 120, 240) for k in (2, 3) for r in (2, 4)]
    + [{"family": "pullback", "k": k, "r": r, "hold": 120} for k in (1.5, 2.5) for r in (2, 3)]
    + [{"family": "london", "stop": s, "r": r} for s in ("far", "mid") for r in (1, 2)]
    + [{"family": "rsi2", "lo": lo, "hold": 24} for lo in (5, 10)]
)


def name(cfg):
    return "-".join(f"{k}={v}" for k, v in cfg.items())


def run(paths):
    data = {}
    for p in paths:
        sym = Path(p).stem.split("_")[0]
        df = load(p)
        data[sym] = (df, indicators(df))
    rows = []
    for cfg in GRID:
        per = {}
        for sym, (df, ind) in data.items():
            t = simulate(sym, df, ind, cfg)
            per[sym] = t
        rows.append((cfg, per))
    return data, rows


def summarize(rows, symbols):
    out = []
    for cfg, per in rows:
        tr = [(t, r) for s in symbols for (t, r, _) in per[s] if t < TRAIN_END]
        ho = [(t, r) for s in symbols for (t, r, _) in per[s] if t >= TRAIN_END]
        f = lambda xs: {"n": len(xs), "meanR": float(np.mean([r for _, r in xs])) if xs else None,
                        "win": float(np.mean([r > 0 for _, r in xs])) if xs else None}
        out.append({"cfg": cfg, "train": f(tr), "holdout": f(ho)})
    return out


if __name__ == "__main__":
    data, rows = run(sys.argv[2:])
    res = summarize(rows, list(data))
    Path(sys.argv[1]).write_text(json.dumps({"status": "OFFLINE_RESEARCH_ONLY", "orders_sent": False,
                                            "symbols": list(data), "train_end": str(TRAIN_END),
                                            "rows": res}, default=str, indent=1))
