"""Build strictly closed UTC-aligned 4h OHLCV bars from contiguous 5m rows.

Research-only helper; requires complete 48-row buckets and never emits partial 4h
bars. Feed the output to research_closed_candle_score_replay.replay_symbol().
"""
from futures_engine.research_closed_candle_score_replay import (
    FIVE_MS, FOUR_MS, _validate,
)

ROWS_PER_FOUR_HOURS = FOUR_MS // FIVE_MS


def aggregate_closed_four_hour(five):
    _validate(five, FIVE_MS)
    output = []
    bucket = []
    bucket_start = None
    for row in five:
        start = row[0] - row[0] % FOUR_MS
        if start != bucket_start:
            if bucket and len(bucket) == ROWS_PER_FOUR_HOURS and bucket[0][0] == bucket_start:
                output.append(_combine(bucket_start, bucket))
            bucket_start, bucket = start, []
        bucket.append(row)
    if bucket and len(bucket) == ROWS_PER_FOUR_HOURS and bucket[0][0] == bucket_start:
        output.append(_combine(bucket_start, bucket))
    return output


def _combine(start, rows):
    if len(rows) != ROWS_PER_FOUR_HOURS or rows[0][0] != start:
        raise ValueError("partial_four_hour_bucket")
    return [start, rows[0][1], max(r[2] for r in rows),
            min(r[3] for r in rows), rows[-1][4],
            sum(r[5] for r in rows)]
