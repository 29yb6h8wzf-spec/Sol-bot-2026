"""Strict offline ingestion boundary for Binance USDT-M closed historical klines.

Caller must obtain data from a trusted, audited read-only source and pass
its recorded provenance. This module never fetches network data or trades.
"""
from hashlib import sha256
import json
from .offline_plan_replay import D, replay

ALLOWED_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"}
INTERVAL_MS = 300000

def replay_verified_history(plan, history):
    """Fail closed unless source, symbol, time and completeness are documented.

    history = {exchange, market, symbol, interval, fetched_at_ms,
               closed_through_ms, klines: [[open_ms, open, high, low, close], ...]}
    """
    if not isinstance(plan, dict) or not isinstance(history, dict):
        raise ValueError("invalid_inputs")
    if history.get("exchange") != "BINANCE" or history.get("market") != "USDT_M_FUTURES":
        raise ValueError("unverified_exchange_market")
    if history.get("interval") != "5m":
        raise ValueError("unsupported_interval")
    symbol = history.get("symbol")
    if symbol not in ALLOWED_SYMBOLS:
        raise ValueError("unsupported_symbol")
    plan_symbol = plan.get("symbol")
    if plan_symbol not in (symbol, symbol.replace("USDT", "/USDT:USDT")):
        raise ValueError("plan_history_symbol_mismatch")
    fetched = history.get("fetched_at_ms")
    closed_through = history.get("closed_through_ms")
    if type(fetched) is not int or type(closed_through) is not int or fetched <= 0:
        raise ValueError("invalid_provenance_times")
    if closed_through > fetched or closed_through % INTERVAL_MS:
        raise ValueError("invalid_closed_through")
    klines = history.get("klines")
    if not isinstance(klines, list) or not klines:
        raise ValueError("missing_klines")
    for row in klines:
        if not isinstance(row, (list, tuple)) or len(row) != 5 or type(row[0]) is not int:
            raise ValueError("invalid_kline")
        if row[0] + INTERVAL_MS > closed_through:
            raise ValueError("unclosed_candle")
        for v in row[1:]:
            if D(v) <= 0:
                raise ValueError("invalid_kline_price")
    if klines[-1][0] + INTERVAL_MS != closed_through:
        raise ValueError("incomplete_closed_history")
    # Content-addressed audit fingerprint. It proves repeatability, not
    # authenticity of the upstream source.
    canonical = json.dumps(history, sort_keys=True, separators=(",", ":"), default=str)
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    result = replay(plan, klines, interval_ms=INTERVAL_MS)
    return {"source": "BINANCE_USDT_M_HISTORICAL_CLAIM_UNVERIFIED",
            "history_sha256": digest,
            "closed_through_ms": closed_through,
            "result": result,
            "orders_sent": False}
