"""Research-only forex helpers for FTMO: 4h resampling and cost conversion.

No orders, no network. FTMO cost inputs (spread in pips, commission per lot,
swap) must come from the MT5/cTrader symbol specification of the account used.
"""
from decimal import Decimal as D, InvalidOperation

FIVE_MS = 300000
FOUR_H_MS = 14400000


def resample_4h(five):
    """UTC-aligned 4h candles built from closed 5m rows [open_ms,o,h,l,c,v].

    MT5 H4 bars are aligned to broker server time (UTC+2/+3), which does not
    match UTC 4h boundaries, so we rebuild 4h bars from 5m ourselves.
    Buckets at a market open/close may be partial; they are kept.
    """
    out = []
    for row in five:
        t, o, h, l, c, v = row
        bucket = t - t % FOUR_H_MS
        if out and out[-1][0] == bucket:
            cur = out[-1]
            cur[2] = max(cur[2], D(str(h)))
            cur[3] = min(cur[3], D(str(l)))
            cur[4] = D(str(c))
            cur[5] += D(str(v))
        else:
            if out and bucket < out[-1][0]:
                raise ValueError("unsorted_candles")
            out.append([bucket, D(str(o)), D(str(h)), D(str(l)), D(str(c)), D(str(v))])
    return out


def forex_costs(*, price, spread_pips, commission_round_turn_per_lot, pip,
                lot_units=100000, quote_to_usd="1"):
    """Convert FTMO forex costs into walk-forward fractions of notional.

    quote_to_usd: USD value of 1 unit of the quote currency (1 for EURUSD,
    1/price for USDJPY). Returns fee_rate (per side) and spread_rate (full spread).
    """
    try:
        price, spread_pips, commission, pip, lot_units, q = (
            D(str(x)) for x in (price, spread_pips, commission_round_turn_per_lot, pip, lot_units, quote_to_usd))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("invalid_costs") from None
    if not all(x.is_finite() for x in (price, spread_pips, commission, pip, lot_units, q)):
        raise ValueError("invalid_costs")
    if price <= 0 or pip <= 0 or lot_units <= 0 or q <= 0 or spread_pips < 0 or commission < 0:
        raise ValueError("invalid_costs")
    notional_usd = lot_units * price * q
    return {"fee_rate": str(commission / 2 / notional_usd), "spread_rate": str(spread_pips * pip / price)}


def load_m5_tsv(path, *, max_fill_minutes=240):
    """Load a tab/comma separated M5 file (Time,Open,High,Low,Close,Volume; UTC).

    Missing mid-session bars (quiet periods, gold's daily break) up to
    max_fill_minutes are filled with flat zero-volume candles at the prior
    close so the walk-forward sees a regular grid. Longer gaps are left in
    place and must be weekend/holiday closures or the replay rejects them.
    """
    import csv
    from datetime import datetime, timezone
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.readline()
        delim = "\t" if "\t" in sample else ","
        for raw in csv.reader(fh, delimiter=delim):
            if not raw:
                continue
            t = int(datetime.strptime(raw[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)
            if t % FIVE_MS:
                raise ValueError("misaligned_candle")
            o, h, l, c, v = (D(x) for x in raw[1:6])
            if rows and t <= rows[-1][0]:
                raise ValueError("unsorted_candles")
            if rows:
                gap = t - rows[-1][0]
                if FIVE_MS < gap <= max_fill_minutes * 60000:
                    prev = rows[-1][4]
                    for k in range(rows[-1][0] + FIVE_MS, t, FIVE_MS):
                        rows.append([k, prev, prev, prev, prev, D(0)])
            rows.append([t, o, h, l, c, v])
    return rows
