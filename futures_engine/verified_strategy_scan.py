"""Read-only 5m/4h strategy scanner using Binance USDT-M candles.

Scores are heuristic conditions, not verified execution authorization.
No SQS publication, exchange credentials, or order placement.
"""
import json
from futures_engine.market import closed_futures_bars
from futures_engine.verified_candidate_audit import SYMBOLS, audit_candidate
from strategies import candidates


def to_strategy_candles(bars):
    result = []
    for bar in bars:
        result.append({
            "time": int(bar[0]),
            "high": float(bar[2]),
            "low": float(bar[3]),
            "close": float(bar[4]),
            "volume": float(bar[5]),
        })
    return result


def evaluate(symbol, *, loader=closed_futures_bars, now_ms=None):
    if symbol not in SYMBOLS:
        raise ValueError("unsupported symbol")
    datasets = {}
    for timeframe, duration in (("5m", 300000), ("4h", 14400000)):
        exchange, market, bars = loader(symbol, timeframe)
        try:
            audit_candidate(symbol, bars, None, now_ms=now_ms,
                            timeframe_ms=duration)
            if len(bars) < 100:
                raise ValueError("insufficient indicator history")
            datasets[timeframe] = to_strategy_candles(bars)
        finally:
            if hasattr(exchange, "close"):
                exchange.close()
    setups, indicators = candidates(datasets["5m"], datasets["4h"])
    eligible = [
        {"strategy": s["strategy"], "direction": s["direction"],
         "score": s["score"], "reason": s["reason"]}
        for s in setups if isinstance(s.get("score"), int)
        and 85 <= s["score"] <= 100
    ]
    return {
        "symbol": symbol,
        "closed_5m_candle_ms": datasets["5m"][-1]["time"],
        "closed_4h_candle_ms": datasets["4h"][-1]["time"],
        "candidates_85_plus": eligible,
        "status": "RESEARCH_ONLY",
        "score_verified_independently": False,
        "sqs_sent": False,
        "orders_sent": False,
    }


def main():
    for symbol in SYMBOLS:
        try:
            print(json.dumps(evaluate(symbol), ensure_ascii=False))
        except Exception as exc:
            print(json.dumps({"symbol": symbol, "status": "BLOCKED",
                              "reason": str(exc), "sqs_sent": False,
                              "orders_sent": False}))


if __name__ == "__main__":
    main()
