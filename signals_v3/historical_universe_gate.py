"""Validate point-in-time historical universe coverage before dynamic replay.

Historical OHLCV alone cannot establish bid/ask depth or contemporaneous
spreads. Require explicit time-stamped snapshots; never backfill from today's
exchangeInfo or ticker data. No exchange connectivity or orders.
"""
import csv
from math import isfinite
from pathlib import Path
from signals_v3.dynamic_universe import UniverseObservation,select_universe, _SYMBOL_PATTERN

COLUMNS=("symbol","observed_at_ms","last_price_usd","quote_volume_24h_usd",
         "spread_bps","bid_depth_10bps_usd","ask_depth_10bps_usd",
         "min_notional_usd","status","contract_type","quote_asset")

def load_snapshots(path):
    with Path(path).open(newline="") as f:
        reader=csv.DictReader(f)
        if reader.fieldnames is None or len(reader.fieldnames)!=len(COLUMNS) or set(reader.fieldnames)!=set(COLUMNS):
            raise ValueError("invalid_universe_snapshot_schema")
        observations=[]
        seen_keys=set()
        for row in reader:
            if None in row or any(v is None or not isinstance(v,str) or not v.strip() for v in row.values()):
                raise ValueError("invalid_universe_snapshot_row")
            try:
                timestamp=int(row["observed_at_ms"])
                if timestamp < 0 or str(timestamp) != row["observed_at_ms"]:
                    raise ValueError("invalid_universe_snapshot_row")
                # Python float() accepts whitespace and underscore separators that
                # are ambiguous in external CSV evidence. Reject them explicitly.
                if any(row[key] != row[key].strip() or "_" in row[key]
                       for key in COLUMNS[2:8]):
                    raise ValueError("invalid_universe_snapshot_row")
                numeric={key:float(row[key]) for key in COLUMNS[2:8]}
            except (ValueError,TypeError,OverflowError) as exc:
                raise ValueError("invalid_universe_snapshot_row") from exc
            key=(row["symbol"],timestamp)
            if key in seen_keys:
                raise ValueError("duplicate_historical_universe_observation")
            seen_keys.add(key)
            if not all(isfinite(value) and value>=0 for value in numeric.values()):
                raise ValueError("invalid_universe_snapshot_row")
            observations.append(UniverseObservation(
                symbol=row["symbol"],observed_at_ms=timestamp,
                last_price_usd=numeric["last_price_usd"],
                quote_volume_24h_usd=numeric["quote_volume_24h_usd"],
                spread_bps=numeric["spread_bps"],
                bid_depth_10bps_usd=numeric["bid_depth_10bps_usd"],
                ask_depth_10bps_usd=numeric["ask_depth_10bps_usd"],
                min_notional_usd=numeric["min_notional_usd"],
                status=row["status"],contract_type=row["contract_type"],
                quote_asset=row["quote_asset"]))
    if not observations:raise ValueError("empty_universe_snapshot")
    return tuple(observations)

def verify_decision_snapshot(observations,decision_ms,expected_symbols=None):
    if type(decision_ms) is not int or decision_ms < 0:
        raise ValueError("invalid_decision_timestamp")
    if not observations:raise ValueError("missing_point_in_time_universe")
    if type(observations) not in (tuple,list) or any(type(x) is not UniverseObservation or type(x.symbol) is not str for x in observations):
        raise ValueError("invalid_historical_universe_observations")
    if len({x.symbol for x in observations})!=len(observations):
        raise ValueError("duplicate_symbol_snapshot")
    if expected_symbols is None:
        raise ValueError("missing_historical_market_listing")
    # A historical listing must be an already-materialized ordered snapshot.
    # Generators and other lazy iterables can fail midway or change between reads.
    if type(expected_symbols) not in (tuple,list):
        raise ValueError("invalid_historical_market_listing")
    expected_symbols=tuple(expected_symbols)
    if any(type(s) is not str or not _SYMBOL_PATTERN.fullmatch(s) for s in expected_symbols):
        raise ValueError("invalid_historical_market_listing")
    expected=set(expected_symbols)
    if not expected or len(expected)!=len(expected_symbols):
        raise ValueError("invalid_historical_market_listing")
    observed={x.symbol for x in observations}
    if observed!=expected:
        raise ValueError("incomplete_historical_universe")
    accepted,reasons=select_universe(observations,decision_ms)
    return {"decision_ms":decision_ms,"eligible_symbols":accepted,
            "rejected_reasons":{k:v for k,v in reasons.items() if v!="eligible"},
            "historical_universe_complete":True}
