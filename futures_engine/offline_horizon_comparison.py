"""Offline-only sensitivity comparison for existing indicative research plans.

The plans are never executable; no networking, order placement, or secrets.
Every scenario uses the same history and cost inputs. The unbounded case is
not force-closed at the end of the supplied data.
"""
from .offline_plan_replay import replay

HORIZONS_MINUTES = (15, 30, 60, 90)


def compare(plan, candles, *, horizons=HORIZONS_MINUTES,
            interval_ms=300000, fee_rate="0.0006",
            slippage_rate="0.0005", initial_equity="150"):
    if not isinstance(horizons, (list, tuple)) or not horizons:
        raise ValueError("invalid_horizons")
    if len(set(horizons)) != len(horizons):
        raise ValueError("duplicate_horizons")
    outcomes = {}
    for minutes in horizons:
        if type(minutes) is not int:
            raise ValueError("invalid_horizon_minutes")
        outcomes[str(minutes)] = replay(
            plan, candles, interval_ms=interval_ms, fee_rate=fee_rate,
            slippage_rate=slippage_rate, initial_equity=initial_equity,
            max_holding_minutes=minutes)
    return {"status": "OFFLINE_SENSITIVITY_ONLY", "orders_sent": False,
            "horizons_minutes": list(horizons), "results": outcomes}


def compare_research_open_time(plan, *, signal_candle_open_ms, candles,
                               horizons=HORIZONS_MINUTES,
                               fee_rate="0.0006", slippage_rate="0.0005",
                               initial_equity="150"):
    """Safely bridge a verified 5m research candle OPEN timestamp into replay.

    Archived research rows call the open time closed_5m_candle_ms; this
    identifies the LAST CLOSED candle, not the time at which it closed.
    Never replay entry during the signal candle. No caller data is mutated.
    """
    interval_ms = 300000
    if (type(signal_candle_open_ms) is not int or
        signal_candle_open_ms < 0 or
        signal_candle_open_ms % interval_ms):
        raise ValueError("invalid_research_candle_open")
    if not isinstance(plan, dict) or plan.get("closed_5m_candle_ms") != signal_candle_open_ms:
        raise ValueError("research_plan_timestamp_mismatch")
    normalized = dict(plan)
    normalized["closed_5m_candle_ms"] = signal_candle_open_ms + interval_ms
    result = compare(normalized, candles, horizons=horizons,
                     interval_ms=interval_ms, fee_rate=fee_rate,
                     slippage_rate=slippage_rate,
                     initial_equity=initial_equity)
    return {**result, "research_signal_candle_open_ms": signal_candle_open_ms,
            "first_possible_entry_candle_open_ms": signal_candle_open_ms + interval_ms}
