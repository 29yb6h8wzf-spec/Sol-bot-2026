"""Validate point-in-time historical universe coverage before dynamic replay.

Historical OHLCV alone cannot establish bid/ask depth or contemporaneous
spreads. Require explicit time-stamped snapshots; never backfill from today's
exchangeInfo or ticker data. No exchange connectivity or orders.
"""
import csv
from pathlib import Path
from signals_v3.dynamic_universe import UniverseObservation,select_universe

COLUMNS=("symbol","observed_at_ms","last_price_usd","quote_volume_24h_usd",
         "spread_bps","bid_depth_10bps_usd","ask_depth_10bps_usd",
         "min_notional_usd","status","contract_type","quote_asset")

def load_snapshots(path):
    with Path(path).open(newline="") as f:
        reader=csv.DictReader(f)
        if reader.fieldnames is None or set(reader.fieldnames)!=set(COLUMNS):
            raise ValueError("invalid_universe_snapshot_schema")
        observations=[]
        for row in reader:
            observations.append(UniverseObservation(
                symbol=row["symbol"],observed_at_ms=int(row["observed_at_ms"]),
                last_price_usd=float(row["last_price_usd"]),
                quote_volume_24h_usd=float(row["quote_volume_24h_usd"]),
                spread_bps=float(row["spread_bps"]),
                bid_depth_10bps_usd=float(row["bid_depth_10bps_usd"]),
                ask_depth_10bps_usd=float(row["ask_depth_10bps_usd"]),
                min_notional_usd=float(row["min_notional_usd"]),
                status=row["status"],contract_type=row["contract_type"],
                quote_asset=row["quote_asset"]))
    if not observations:raise ValueError("empty_universe_snapshot")
    return tuple(observations)

def verify_decision_snapshot(observations,decision_ms,expected_symbols=None):
    if not observations:raise ValueError("missing_point_in_time_universe")
    if len({x.symbol for x in observations})!=len(observations):
        raise ValueError("duplicate_symbol_snapshot")
    if expected_symbols is None:
        raise ValueError("missing_historical_market_listing")
    expected_symbols=tuple(expected_symbols)
    expected=set(expected_symbols)
    if not expected or len(expected)!=len(tuple(expected_symbols)) or any(not s.endswith("USDT") for s in expected):
        raise ValueError("invalid_historical_market_listing")
    observed={x.symbol for x in observations}
    if observed!=expected:
        raise ValueError("incomplete_historical_universe")
    accepted,reasons=select_universe(observations,decision_ms)
    return {"decision_ms":decision_ms,"eligible_symbols":accepted,
            "rejected_reasons":{k:v for k,v in reasons.items() if v!="eligible"},
            "historical_universe_complete":True}
