# Exposure variants (2026-11-24), US100 FTMO data 2021-10..2026-11, Phase 1 bootstrap (5-day blocks)
| Variant (TOM/DIP/BTM x ISC) | ann | Sharpe | max DD | worst day | 63d pass/fail | 126d pass/fail |
|---|---|---|---|---|---|---|
| A 2/2/2 (live v1.01) | +39.2% | 1.06 | 25.3% | -11.42% | 51/41 | 56/44 |
| B 2/2/2, TOM+DIP overnight <= 2x | +39.8% | 1.11 | 25.5% | -11.42% | 54/36 | 60/39 |
| C 1.5/1.5/1.5 | +29.4% | 1.06 | 19.3% | -8.56% | 48/28 | 62/34 |
| D 1/2/2 | +38.1% | 1.14 | 20.8% | -9.16% | 53/29 | 64/34 |
| F 1/2/2 + overnight cap 2x | +38.4% | 1.17 | 21.0% | -9.16% | 53/29 | 64/33 |
Chosen for v1.02: D (TOM 1x) plus a hard gross cap of 5x checked before every entry.
Caveat: in-sample choice; TOM was weak on US100 in this window but robust over 1950-2025 on US500.
