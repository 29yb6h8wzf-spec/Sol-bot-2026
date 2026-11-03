"""Independent, read-only verifier for SignalPilot research candidates.

Recomputes the candidate using fresh Binance Futures candles via the
existing strategy scanner. This does not authorize or place orders.
"""
import time

SYMBOLS = frozenset(("BTC/USDT:USDT", "ETH/USDT:USDT",
                     "SOL/USDT:USDT", "XRP/USDT:USDT"))
ALIASES = {s.replace("/USDT:USDT", "USDT"): s for s in SYMBOLS}


def verify(payload, *, scan=None, now=None):
    if not isinstance(payload, dict):
        raise ValueError("invalid_payload")
    symbol = ALIASES.get(payload.get("symbol"), payload.get("symbol"))
    strategy = payload.get("strategy")
    direction = payload.get("direction")
    candle = payload.get("closed_5m_candle_ms")
    if symbol not in SYMBOLS or direction not in ("long", "short"):
        raise ValueError("invalid_symbol_or_direction")
    compact = strategy is None and candle is None
    if not compact:
        if not isinstance(strategy, str) or not strategy or len(strategy) > 80:
            raise ValueError("invalid_strategy")
        if type(candle) is not int or candle <= 0 or candle % 300000:
            raise ValueError("invalid_candle")
    now = int(time.time()) if now is None else int(now)
    if not compact and not 0 <= now * 1000 - (candle + 300000) <= 420000:
        raise ValueError("stale_candle")
    if scan is None:
        from futures_engine.verified_strategy_scan import evaluate
        scan = evaluate
    result = scan(symbol, now_ms=now * 1000)
    observed_candle = result.get("closed_5m_candle_ms")
    if result.get("symbol") != symbol or type(observed_candle) is not int:
        raise ValueError("candle_mismatch")
    if compact:
        # Legacy inbox messages omit strategy/candle. Match only one freshly
        # recomputed candidate and require signal timing near candle close.
        sent = payload.get("timestamp")
        close_ms = observed_candle + 300000
        if type(sent) is not int or not 0 <= sent * 1000 - close_ms <= 120000:
            raise ValueError("compact_signal_not_at_candle_close")
        if not 0 <= now * 1000 - close_ms <= 420000:
            raise ValueError("stale_candle")
    elif observed_candle != candle:
        raise ValueError("candle_mismatch")
    if result.get("status") != "RESEARCH_ONLY":
        raise ValueError("scanner_not_ready")
    candidates = result.get("candidates_85_plus", [])
    matches = [c for c in candidates if isinstance(c, dict)
               and (compact or c.get("strategy") == strategy)
               and c.get("direction") == direction.upper()
               and type(c.get("score")) is int and 85 <= c["score"] <= 100
               and isinstance(c.get("verification"), dict)
               and bool(c["verification"])]
    if len(matches) != 1:
        raise ValueError("independent_candidate_mismatch")
    return {
        "signal_id": payload["signal_id"],
        "symbol": symbol,
        "strategy": matches[0]["strategy"],
        "direction": direction,
        "score": matches[0]["score"],
        "source": "verified_85_score_engine",
        "verification": matches[0]["verification"],
    }
