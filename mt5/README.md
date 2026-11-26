# TurnOfMonthEA (MT5) — FTMO Free Trial first

Strategy and evidence: `docs/FTMO_TURN_OF_MONTH_2026-11-23.md`, `docs/FTMO_CALENDAR_2026-11-23.md`.

## What it does
- Buys US500 at 22:50 server time (15:50 New York) on the last US trading day of the month.
- Sells at 22:50 server time on the 3rd US trading day of the new month.
- Position notional = initial capital × `InpNotionalMultiple` (default 1.0 — research shows more leverage mainly adds daily-loss failures).
- Guards: closes everything and stops for the day if equity falls 3.5 % of initial capital below the midnight balance; disables itself at −8 % of initial capital; 5 % catastrophic stop on every position; safety exit after 9 days.

Next turns (2026 holiday list): enter 30 Nov → exit 3 Dec; enter 31 Dec → exit 6 Jan; enter 29 Jan → exit 3 Feb.

## Install (Windows MT5 or a Windows VPS — the phone app cannot run EAs)
1. MT5 → File → Open Data Folder → `MQL5/Experts/` → copy `TurnOfMonthEA.mq5`.
2. In MetaEditor open it and press Compile (F7). Fix nothing silently — send any error.
3. Market Watch: find the exact S&P 500 name (e.g. `US500.cash`) and set `InpSymbol`.
4. Set `InpInitialCapital` to the account size. Attach to any chart, enable Algo Trading.
5. Check the Experts log for "TurnOfMonthEA ready".

## Known limits
- FTMO resets the daily limit at 00:00 CE(S)T; the EA anchors on server midnight (1 h earlier). The 3.5 % guard leaves margin for this.
- Lot sizing assumes a USD account and USD-quoted index; verify the first trade's notional.
- Update `InpHolidays` every year (NYSE calendar).
- Not compiled in this environment; first run must be on the Free Trial.
