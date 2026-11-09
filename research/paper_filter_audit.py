"""Explain each exact strategy entry gate on immutable closed candles.

Research-only diagnostics: NEVER creates a signal, changes score thresholds,
uses exchange credentials, or places an order. Conditions mirror strategies.py.
"""
from strategies import adx, bands, candidates, ema_series, rsi


def audit_filters(five, four):
    if len(five) < 100 or len(four) < 100:
        raise ValueError("insufficient closed history for filter audit")
    closes = [c["close"] for c in five]
    four_closes = [c["close"] for c in four]
    e20 = ema_series(four_closes, 20)[-1]
    e50 = ema_series(four_closes, 50)[-1]
    e9 = ema_series(closes, 9)
    e21 = ema_series(closes, 21)
    macd = [a - b for a, b in zip(
        ema_series(closes, 12), ema_series(closes, 26),
    )]
    signal = ema_series(macd, 9)
    lower, upper = bands(closes)
    prev_lower, prev_upper = bands(closes[:-1])
    strength = adx(four)
    momentum = rsi(closes)
    avg_volume = sum(c["volume"] for c in five[-13:-1]) / 12
    vol_ratio = five[-1]["volume"] / avg_volume if avg_volume else 0
    last, previous = closes[-1], closes[-2]

    def condition(name, actual, comparator, threshold):
        return {
            "name": name, "actual": actual, "comparison": comparator,
            "threshold": threshold,
            "passed": {
                ">": actual > threshold, ">=": actual >= threshold,
                "<": actual < threshold, "<=": actual <= threshold,
            }[comparator],
        }

    reports = []
    for side in ("LONG", "SHORT"):
        up = side == "LONG"
        ema = [
            condition("four_hour_ema_trend", e20, ">" if up else "<", e50),
            condition("previous_close_reclaim", previous, "<=" if up else ">=", e9[-2]),
            condition("current_close_reclaim", last, ">" if up else "<", e9[-1]),
            condition("ema_9_21_alignment", e9[-1], ">" if up else "<", e21[-1]),
            condition("four_hour_adx", strength, ">=", 20),
            condition("relative_volume", vol_ratio, ">=", 0.8),
        ]
        boll = [
            condition("four_hour_adx", strength, "<", 25),
            condition("previous_band_break", previous, "<" if up else ">",
                      prev_lower if up else prev_upper),
            condition("current_band_reclaim", last, ">" if up else "<",
                      lower if up else upper),
            condition("rsi", momentum, "<" if up else ">", 45 if up else 55),
        ]
        macd_gates = [
            condition("previous_macd_crossover", macd[-2], "<=" if up else ">=",
                      signal[-2]),
            condition("current_macd_crossover", macd[-1], ">" if up else "<",
                      signal[-1]),
            condition("relative_volume", vol_ratio, ">=", 1.2),
            condition("rsi", momentum, ">" if up else "<", 50),
        ]
        for strategy, gates in (
            ("EMA_ADX", ema), ("RSI_BOLL", boll), ("MACD_VOLUME", macd_gates),
        ):
            reports.append({
                "strategy": strategy, "direction": side,
                "passed": all(g["passed"] for g in gates),
                "failed_filters": [g["name"] for g in gates if not g["passed"]],
                "conditions": gates,
            })

    # Detect diagnostic drift immediately instead of presenting incorrect
    # blockers. This is not used to authorize a signal.
    actual, _ = candidates(five, four)
    expected = {(x["strategy"], x["direction"]) for x in reports if x["passed"]}
    found = {(x["strategy"], x["direction"]) for x in actual}
    if expected != found:
        raise ValueError("strategy filter audit drift")
    return reports
