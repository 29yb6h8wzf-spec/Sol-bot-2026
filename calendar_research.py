"""Research-only calendar-effect scan on S&P 500 daily closes 1950-2025 (no orders).

Discipline: every rule is fixed in advance or chosen on 1950-1989 only, then judged on
1990-2025 and decade by decade. Excess = return minus the average daily return of the
same decade (so bull/bear decades do not masquerade as an effect).
Effects:
  tom(-a,+b)   close of day -a before month end ... close of trading day b of new month
  preholiday   the last trading day before a weekday market closure (US holidays)
  weekday      Monday..Friday close-to-close
"""
import sys
import numpy as np
import pandas as pd

d = pd.read_csv(sys.argv[1], parse_dates=["Date"]).set_index("Date")
c = d["Close"][d.index >= "1950-01-01"]
r = c.pct_change().fillna(0)
dates = c.index
n = len(c)
dec = (dates.year // 10) * 10
base = r.groupby(dec).transform("mean")
ex = r - base

m = dates.to_period("M")
last = np.r_[m[1:] != m[:-1], False]
pos_in_month = pd.Series(1, index=dates).groupby(m).cumsum().to_numpy()       # 1..N
from_end = pd.Series(1, index=dates)[::-1].groupby(m[::-1]).cumsum()[::-1].to_numpy()  # 1 = last day

gap = np.r_[(dates[1:] - dates[:-1]).days, 1]
wd = dates.dayofweek.to_numpy()
preholiday = ((gap > 1) & (wd != 4)) | ((gap > 3) & (wd == 4))


def window_mask(a, b):
    """days whose return is earned by holding from close of day `a` before month end to close of day b."""
    return ((from_end <= a - 1) & (from_end >= 1) & ~(from_end == 0)) & (a > 1) | (pos_in_month <= b)


def tom_mask(a, b):
    # returns earned on the last (a-1) days of the month and the first b days of the next
    return (from_end <= a - 1) | (pos_in_month <= b)


def stats(mask, label):
    s = ex[mask]; raw = r[mask]
    t = s.mean() / s.std() * len(s) ** .5
    per = s.groupby(dec[mask]).mean() * 100
    early, late = s[dates[mask].year < 1990], s[dates[mask].year >= 1990]
    print(f"{label:22} days={mask.sum():6} excess/day={s.mean()*100:+.3f}% t={t:+.1f} | "
          f"1950-89 {early.mean()*100:+.3f}% 1990-25 {late.mean()*100:+.3f}% | "
          f"decades>0: {(per>0).sum()}/{len(per)}  min decade {per.min():+.3f}%", flush=True)
    return per


if __name__ == "__main__":
    print("Average daily return all days:", round(r.mean() * 100, 3), "%")
    stats(tom_mask(1, 3), "TOM -1..+3 (current)")
    for a, b in ((2, 3), (1, 4), (3, 4), (1, 2), (4, 4)):
        stats(tom_mask(a, b), f"TOM -{a}..+{b}")
    ph = preholiday & ~tom_mask(1, 3)
    stats(ph, "pre-holiday (non-TOM)")
    for k, name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri"]):
        stats((wd == k) & ~tom_mask(1, 3) & ~preholiday, f"weekday {name} (other)")
    mid = (pos_in_month >= 4) & (from_end >= 2) & ~preholiday
    stats(mid, "rest of month")
