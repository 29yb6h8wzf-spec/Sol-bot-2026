"""Fail-closed trade-window exclusion gate for Signals V2 research.

All interval bounds are UTC milliseconds, half-open [start,end). A trade is
blocked if its indicator lookback, entry-to-exit, or holding horizon intersects
any excluded interval. Never fabricate missing candles.
"""
import json
from pathlib import Path

GAP_START=1793145600000
GAP_END=1793232000000
ALLOWED_SYMBOLS=("SOLUSDT","XRPUSDT")
def validate_manifest(manifest):
    if manifest.get("status")!="PASS_WITH_EXCLUSIONS":raise ValueError("unverified_mismatch_manifest")
    if manifest.get("months_scanned")!=48:raise ValueError("incomplete_month_scan")
    if manifest.get("fatal_errors"):raise ValueError("fatal_data_errors")
    mismatches=manifest.get("mismatches")
    if not isinstance(mismatches,list) or len(mismatches)!=manifest.get("mismatch_count"):
        raise ValueError("missing_or_truncated_mismatch_list")
    intervals={s:[(GAP_START,GAP_END,"missing_day")] for s in ALLOWED_SYMBOLS}
    for issue in mismatches:
        symbol=issue.get("symbol")
        if symbol not in intervals:raise ValueError("unexpected_symbol")
        start=issue.get("start_ms");end=issue.get("end_exclusive_ms")
        if type(start)!=int or type(end)!=int or start>=end or end-start!=300000:
            raise ValueError("invalid_mismatch_interval")
        if not issue.get("differences"):raise ValueError("missing_mismatch_evidence")
        intervals[symbol].append((start,end,"ohlcv_disagreement"))
    for symbol in intervals:intervals[symbol].sort()
    return intervals

def eligible(intervals,symbol,lookback_start_ms,entry_ms,exit_or_horizon_end_ms):
    if symbol not in ALLOWED_SYMBOLS:raise ValueError("unexpected_symbol")
    if not all(type(v)==int for v in (lookback_start_ms,entry_ms,exit_or_horizon_end_ms)):
        raise ValueError("timestamps_must_be_int_ms")
    if not lookback_start_ms<=entry_ms<exit_or_horizon_end_ms:
        raise ValueError("invalid_trade_window")
    for start,end,reason in intervals[symbol]:
        if lookback_start_ms<end and exit_or_horizon_end_ms>start:
            return False,{"reason":reason,"excluded_start_ms":start,"excluded_end_ms":end}
    return True,None

def load_manifest(path):
    return validate_manifest(json.loads(Path(path).read_text()))

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("manifest");p.add_argument("symbol")
    p.add_argument("lookback_start_ms",type=int);p.add_argument("entry_ms",type=int)
    p.add_argument("horizon_end_ms",type=int)
    a=p.parse_args();print(json.dumps(dict(zip(("eligible","exclusion"),eligible(load_manifest(a.manifest),a.symbol,a.lookback_start_ms,a.entry_ms,a.horizon_end_ms))),indent=2))
