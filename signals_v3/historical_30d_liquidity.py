"""Research-only 30 closed UTC-day quote-volume evidence gate.

Not wired into execution or the legacy 24h selector. Missing daily archives
must fail closed; never substitute current exchange ticker volume.
"""
from dataclasses import dataclass
import re
from math import isfinite

DAY_MS = 86_400_000
MIN_AVG_DAILY_QUOTE_USD = 20_000_000.0
LOOKBACK_DAYS = 30
_SYMBOL_PATTERN = re.compile(r"[A-Z0-9]{2,30}USDT\Z")


@dataclass(frozen=True)
class ClosedDailyVolume:
    symbol: str
    day_start_ms: int
    quote_volume_usd: float


def verify_30d_liquidity(records, symbol, decision_ms):
    """Return verified trailing average, or raise ValueError.

    Requires 30 distinct consecutive *closed* UTC calendar days preceding the
    UTC day of decision. This conservative choice never uses partial-day data.
    Records are evidence inputs, not proof of provider authenticity.
    """
    if type(decision_ms) is not int or decision_ms < 0:
        raise ValueError("invalid_decision_timestamp")
    if type(symbol) is not str or _SYMBOL_PATTERN.fullmatch(symbol) is None:
        raise ValueError("invalid_volume_symbol")
    if type(records) not in (tuple, list):
        raise ValueError("invalid_daily_volume_records")
    day_start = (decision_ms // DAY_MS) * DAY_MS
    if day_start < LOOKBACK_DAYS * DAY_MS:
        raise ValueError("insufficient_historical_calendar")
    expected = {day_start - offset * DAY_MS for offset in range(1, LOOKBACK_DAYS + 1)}
    seen = set()
    total = 0.0
    for record in records:
        if type(record) is not ClosedDailyVolume or record.symbol != symbol:
            raise ValueError("invalid_daily_volume_record")
        timestamp = record.day_start_ms
        value = record.quote_volume_usd
        if type(timestamp) is not int or timestamp not in expected:
            raise ValueError("non_point_in_time_daily_volume")
        if timestamp in seen:
            raise ValueError("duplicate_daily_volume")
        if type(value) not in (int, float) or value < 0:
            raise ValueError("invalid_daily_volume_value")
        try:
            finite = isfinite(value)
        except (OverflowError, ValueError):
            finite = False
        if not finite:
            raise ValueError("invalid_daily_volume_value")
        seen.add(timestamp)
        total += value
    if seen != expected or not isfinite(total):
        raise ValueError("incomplete_30d_volume_evidence")
    average = total / LOOKBACK_DAYS
    return {
        "symbol": symbol,
        "decision_ms": decision_ms,
        "lookback_days": LOOKBACK_DAYS,
        "average_daily_quote_volume_usd": average,
        "meets_30d_liquidity_threshold": average >= MIN_AVG_DAILY_QUOTE_USD,
        "provider_authenticity_verified": False,
    }
