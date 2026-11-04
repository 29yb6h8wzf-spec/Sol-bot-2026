"""Deterministic economic-event identity for independently verified research signals.

Never derive an idempotency key from untrusted Telegram payload fields.
This module does not place orders or authorize execution.
"""
import hashlib
import json

SYMBOLS = frozenset({"BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT"})


def verified_event_key(verified):
    if not isinstance(verified, dict):
        raise ValueError("invalid_verification")
    if verified.get("source") != "verified_85_score_engine":
        raise ValueError("unverified_source")
    symbol, strategy, direction = (verified.get(k) for k in ("symbol", "strategy", "direction"))
    candle = verified.get("closed_5m_candle_ms")
    score = verified.get("score")
    if symbol not in SYMBOLS or not isinstance(strategy, str) or not 1 <= len(strategy) <= 80:
        raise ValueError("invalid_strategy_or_symbol")
    if direction not in ("long", "short") or type(candle) is not int or candle <= 0 or candle % 300000:
        raise ValueError("invalid_direction_or_candle")
    if type(score) is not int or not 85 <= score <= 100:
        raise ValueError("invalid_verified_score")
    if not isinstance(verified.get("verification"), dict) or not verified["verification"]:
        raise ValueError("missing_independent_verification")
    canonical = json.dumps(["binance-usdtm", symbol, "5m", strategy, direction, candle], separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
