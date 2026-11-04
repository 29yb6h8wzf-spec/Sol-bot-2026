"""Read-only external research comparison for SignalPilot.

Premiss/AlgoVault responses are untrusted observations, NEVER verification,
risk approval, trade signals or order instructions. No API/network calls.
"""
from datetime import datetime, timezone

SYMBOLS = frozenset({"BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"})
CALLS = frozenset({"BUY", "SELL", "HOLD"})
REGIMES = frozenset({"TRENDING_UP", "TRENDING_DOWN", "RANGING", "VOLATILE"})


def compare(signal, algovault=None, premiss=None):
    """Return a shadow-only comparison; no changes to execution eligibility."""
    if not isinstance(signal, dict) or signal.get("symbol") not in SYMBOLS:
        raise ValueError("unsupported_signal")
    direction = signal.get("direction")
    if direction not in ("long", "short"):
        raise ValueError("unsupported_direction")
    out = {"symbol": signal["symbol"], "direction": direction,
           "mode": "SHADOW_RESEARCH_ONLY", "execution_authorized": False,
           "orders_sent": False, "providers": {}}
    if isinstance(algovault, dict):
        call = algovault.get("call")
        coin = algovault.get("coin")
        if coin == signal["symbol"][:-4] and call in CALLS:
            expected = "BUY" if direction == "long" else "SELL"
            out["providers"]["algovault"] = {
                "call": call,
                "agreement": "agree" if call == expected else
                             ("neutral" if call == "HOLD" else "disagree"),
                "regime": algovault.get("regime") if algovault.get("regime") in REGIMES else None,
                "confidence": algovault.get("confidence") if
                    type(algovault.get("confidence")) in (int, float) and
                    0 <= algovault["confidence"] <= 100 else None}
    if isinstance(premiss, dict):
        # A recorded backtest is context only; never treat it as live proof.
        run_id = premiss.get("run_id")
        if isinstance(run_id, str) and 0 < len(run_id) <= 128:
            out["providers"]["premiss"] = {
                "run_id": run_id, "status": "historical_context_only"}
    out["provider_count"] = len(out["providers"])
    return out
