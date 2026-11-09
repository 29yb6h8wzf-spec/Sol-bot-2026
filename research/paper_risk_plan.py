"""Offline paper-only sizing from a closed signal price and fixed risk limits.

This is a deterministic simulation helper, not a live trading approval.
"""
from decimal import ROUND_DOWN, Decimal

from research.paper_signal_adapter import replay_scanner_candidate

D = Decimal


def paper_plan(entry_mid, side, *, capital="150", leverage="2",
               risk_usd="1.50", stop_fraction="0.005",
               reward_multiple="2", quantity_step="0.001"):
    price, equity, lev, risk = map(D, (entry_mid, capital, leverage, risk_usd))
    distance, reward, step = map(D, (stop_fraction, reward_multiple, quantity_step))
    if side not in ("LONG", "SHORT"):
        raise ValueError("invalid side")
    if not (price > 0 and equity > 0 and 0 < lev <= 2 and
            0 < risk <= D("1.50") and 0 < distance <= D("0.02") and
            reward > 0 and step > 0):
        raise ValueError("paper risk limits exceeded")
    # Risk budget includes estimated round-trip taker fees and slippage.
    cost_fraction = D("0.0014")
    unit_risk = price * (distance + cost_fraction)
    max_qty = min(risk / unit_risk, equity * lev / price)
    quantity = (max_qty / step).to_integral_value(rounding=ROUND_DOWN) * step
    if quantity <= 0:
        raise ValueError("paper quantity below step size")
    sign = D(1) if side == "LONG" else D(-1)
    stop = price * (1 - sign * distance)
    target = price * (1 + sign * distance * reward)
    return {
        "entry_mid": str(price), "quantity": str(quantity),
        "stop": str(stop), "target": str(target),
        "estimated_risk_usd": str(quantity * unit_risk),
        "estimated_notional": str(quantity * price),
        "paper_only": True,
    }


def replay_sized_candidate(scan, *, signal_close, future_bars,
                           database_path, candidate_index=0, **risk):
    candidates = scan.get("candidates_85_plus", [])
    if not isinstance(candidates, list) or not 0 <= candidate_index < len(candidates):
        raise ValueError("no eligible scanner candidate")
    plan = paper_plan(signal_close, candidates[candidate_index]["direction"], **risk)
    result = replay_scanner_candidate(
        scan, quantity=plan["quantity"], entry_mid=plan["entry_mid"],
        stop=plan["stop"], target=plan["target"],
        bars=future_bars, database_path=database_path,
        candidate_index=candidate_index,
    )
    result["paper_plan"] = plan
    return result
