"""Independent deterministic check of research candidates; no publishing or orders.

The verifier re-evaluates the strategy from candle inputs, not a claimed score.
"""
import hashlib
import json
from strategies import candidates

SYMBOLS = frozenset(("BTC/USDT:USDT", "ETH/USDT:USDT",
                     "SOL/USDT:USDT", "XRP/USDT:USDT"))
STRATEGIES = frozenset(("EMA_ADX", "RSI_BOLL", "MACD_VOLUME"))


class VerificationError(ValueError):
    pass


def verify_candidate(candidate, *, symbol, five, four):
    if symbol not in SYMBOLS:
        raise VerificationError("unsupported symbol")
    if not isinstance(candidate, dict):
        raise VerificationError("candidate must be object")
    if candidate.get("strategy") not in STRATEGIES:
        raise VerificationError("unknown strategy")
    if candidate.get("direction") not in ("LONG", "SHORT"):
        raise VerificationError("invalid direction")
    if type(candidate.get("score")) is not int or not 85 <= candidate["score"] <= 95:
        raise VerificationError("score outside verified strategy range")
    if len(five) < 100 or len(four) < 100:
        raise VerificationError("insufficient candles")
    if not all(isinstance(c, dict) and all(k in c for k in
               ("time", "high", "low", "close", "volume")) for c in five + four):
        raise VerificationError("invalid candle schema")
    if any(five[i]["time"] - five[i-1]["time"] != 300000
           for i in range(1, len(five))):
        raise VerificationError("5m candle gaps")
    if any(four[i]["time"] - four[i-1]["time"] != 14400000
           for i in range(1, len(four))):
        raise VerificationError("4h candle gaps")
    if any(not isinstance(c["close"], (int, float)) or c["close"] <= 0
           for c in five + four):
        raise VerificationError("invalid prices")
    setups, _ = candidates(five, four)
    matches = [s for s in setups if s["strategy"] == candidate["strategy"]
               and s["direction"] == candidate["direction"]
               and s["score"] == candidate["score"]]
    if len(matches) != 1:
        raise VerificationError("claimed candidate does not match recalculated strategy")
    # Signal identity is tied to symbol, strategy, direction and closed 5m bar.
    identity = {
        "symbol": symbol, "strategy": candidate["strategy"],
        "direction": candidate["direction"], "score": candidate["score"],
        "candle_ms": five[-1]["time"],
    }
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True,
                                      separators=(",", ":")).encode()).hexdigest()
    return {
        **identity, "signal_id": "research-" + digest[:32],
        "status": "RECALCULATED_RESEARCH_CANDIDATE",
        "score_verified_independently": True,
        "execution_authorized": False, "sqs_sent": False,
        "orders_sent": False,
    }
