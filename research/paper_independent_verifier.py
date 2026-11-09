"""Recalculate saved scanner candidates from historical 5m and 4h candles.

The caller must supply independently obtained closed-candle datasets in the
same strategy schema as the scanner. This module never calls an exchange.
"""
from futures_engine.candidate_verifier import verify_candidate


def verify_saved_scan(scan, five, four, *, candidate_index=0):
    if scan.get("status") != "RESEARCH_ONLY":
        raise ValueError("not a research scan")
    if scan.get("orders_sent") is not False or scan.get("sqs_sent") is not False:
        raise ValueError("scanner is not read-only")
    candidates = scan.get("candidates_85_plus")
    if not isinstance(candidates, list) or not 0 <= candidate_index < len(candidates):
        raise ValueError("no eligible scanner candidate")
    if not isinstance(five, list) or not isinstance(four, list) or not five or not four:
        raise ValueError("5m and 4h history required")
    if (five[-1].get("time") != scan.get("closed_5m_candle_ms")
            or four[-1].get("time") != scan.get("closed_4h_candle_ms")):
        raise ValueError("history does not match scanner timestamps")
    candidate = candidates[candidate_index]
    recomputed = verify_candidate(
        candidate, symbol=scan["symbol"], five=five, four=four
    )
    if candidate.get("verification") != recomputed:
        raise ValueError("saved scanner verification differs from recalculation")
    return recomputed
