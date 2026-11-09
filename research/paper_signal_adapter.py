"""Offline-only adapter: research scanner candidate -> durable paper replay.

Requires an actual scanner result and separately supplied closed future candles.
Does not promote heuristic scores to live execution authorization.
"""
import hashlib
import json
from decimal import Decimal

from research.paper_market_replay import replay


def replay_scanner_candidate(scan, *, quantity, entry_mid, stop, target,
                             bars, database_path, candidate_index=0):
    if scan.get("status") != "RESEARCH_ONLY":
        raise ValueError("not a research scanner result")
    if scan.get("orders_sent") is not False or scan.get("sqs_sent") is not False:
        raise ValueError("scanner must be read-only")
    candidates = scan.get("candidates_85_plus")
    if not isinstance(candidates, list) or not 0 <= candidate_index < len(candidates):
        raise ValueError("no eligible scanner candidate")
    candidate = candidates[candidate_index]
    if not isinstance(candidate.get("verification"), dict):
        raise TypeError("missing candidate verification")
    if type(candidate.get("score")) is not int or candidate["score"] < 85:
        raise ValueError("score below scanner threshold")
    verification = candidate["verification"]
    if (verification.get("status") != "RECALCULATED_RESEARCH_CANDIDATE"
            or verification.get("score_verified_independently") is not True
            or verification.get("execution_authorized") is not False
            or verification.get("orders_sent") is not False
            or verification.get("sqs_sent") is not False
            or verification.get("symbol") != scan.get("symbol")
            or verification.get("candle_ms") != scan.get("closed_5m_candle_ms")
            or verification.get("strategy") != candidate.get("strategy")
            or verification.get("direction") != candidate.get("direction")
            or verification.get("score") != candidate.get("score")
            or not str(verification.get("signal_id", "")).startswith("research-")):
        raise ValueError("unverified research candidate")
    side = candidate.get("direction")
    if side not in ("LONG", "SHORT"):
        raise ValueError("invalid candidate direction")
    candle_ms = scan.get("closed_5m_candle_ms")
    if type(candle_ms) is not int or candle_ms < 0 or candle_ms % 1000:
        raise ValueError("invalid signal candle timestamp")
    if not isinstance(bars, list) or not bars:
        raise ValueError("future closed candles required")
    # The scanner timestamps the candle OPEN; the next 5m candle is the first
    # eligible simulated fill. Never replay the signal-forming candle.
    opened_at = (candle_ms + 300000) // 1000
    if any(int(b["open_ms"]) < opened_at * 1000 for b in bars):
        raise ValueError("replay contains signal or earlier candle")
    identity = json.dumps(
        [scan.get("symbol"), candle_ms, candidate.get("strategy"), side],
        separators=(",", ":"), ensure_ascii=True,
    )
    uid = "paper-" + hashlib.sha256(identity.encode()).hexdigest()[:24]
    payload = {
        "symbol": scan["symbol"], "signal_uid": uid, "side": side,
        "quantity": str(Decimal(str(quantity))),
        "entry_mid": str(Decimal(str(entry_mid))),
        "stop": str(Decimal(str(stop))), "target": str(Decimal(str(target))),
        "opened_at": opened_at, "bars": bars,
    }
    result = replay(payload, database_path)
    result["provenance"] = {
        "source": "research_scanner", "strategy": candidate["strategy"],
        "score": candidate["score"], "signal_candle_open_ms": candle_ms,
        "paper_only": True, "live_authorized": False,
    }
    return result
