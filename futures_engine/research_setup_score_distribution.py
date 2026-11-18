"""Offline-only setup score distribution for SOL/XRP research.

This module does not fetch market data, change trading gates, or place orders.
Feed it candidate setups produced by strategies.candidates() in an isolated replay.
"""
from collections import Counter

ALLOWED_SYMBOLS = frozenset(("SOL/USDT:USDT", "XRP/USDT:USDT"))
BANDS = ("below_70", "70_79", "80_84", "85_plus")


def score_band(score):
    if type(score) is not int or score < 0 or score > 100:
        return "invalid_score"
    if score < 70:
        return "below_70"
    if score < 80:
        return "70_79"
    if score < 85:
        return "80_84"
    return "85_plus"


def summarize_setups(scans):
    """Aggregate per-scan strategy outputs, not deduplicated trade opportunities.

    Each scan is {"symbol": ..., "setups": [strategy candidate dictionaries]}.
    A scan with no setups is distinct from a below-threshold setup.
    """
    totals = Counter()
    groups = {}
    for scan in scans:
        if not isinstance(scan, dict) or scan.get("symbol") not in ALLOWED_SYMBOLS:
            raise ValueError("invalid_scan_symbol")
        setups = scan.get("setups")
        if not isinstance(setups, list):
            raise ValueError("invalid_setups")
        symbol = scan["symbol"]
        totals["scans"] += 1
        totals["no_setup_scans"] += not bool(setups)
        for setup in setups:
            if not isinstance(setup, dict):
                raise ValueError("invalid_setup")
            strategy, direction = setup.get("strategy"), setup.get("direction")
            if not isinstance(strategy, str) or not strategy or direction not in ("LONG", "SHORT"):
                raise ValueError("invalid_setup_identity")
            band = score_band(setup.get("score"))
            key = (symbol, strategy, direction)
            bucket = groups.setdefault(key, Counter())
            bucket[band] += 1
            totals[band] += 1
            totals["setups"] += 1
    return {
        "totals": dict(sorted(totals.items())),
        "by_symbol_strategy_direction": [
            {"symbol": symbol, "strategy": strategy, "direction": direction,
             "counts": {band: counts.get(band, 0) for band in (*BANDS, "invalid_score")}}
            for (symbol, strategy, direction), counts in sorted(groups.items())
        ],
        "research_only": True,
        "execution_authorized": False,
    }
