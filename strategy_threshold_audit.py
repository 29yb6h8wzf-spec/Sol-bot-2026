"""Offline-only threshold audit for SignalPilot research candidates.

Never changes the production 85+ gate, never submits orders, and does not
interpret a heuristic score as a win probability.
"""
from collections import Counter

THRESHOLDS = (70, 75, 80, 85)

def summarize(setups):
    if not isinstance(setups, list):
        raise ValueError("invalid_setups")
    scores = []
    by_strategy = Counter()
    for item in setups:
        if not isinstance(item, dict) or type(item.get("score")) is not int:
            raise ValueError("invalid_score")
        score = item["score"]
        if not 0 <= score <= 100:
            raise ValueError("invalid_score")
        scores.append(score)
        by_strategy[str(item.get("strategy", "UNKNOWN"))] += 1
    return {"total_candidates":len(scores),
            "counts_by_threshold":{str(t):sum(score >= t for score in scores) for t in THRESHOLDS},
            "by_strategy":dict(sorted(by_strategy.items())),
            "win_rate_known":False,"orders_sent":False}
