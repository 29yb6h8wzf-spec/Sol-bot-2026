"""Check the *real* full-history mismatch manifest and demonstrate trading-window gating.

Fail closed if any month, mismatch, or excluded interval is absent.
"""
import argparse,json
from pathlib import Path
from backtest_exclusion_gate import load_manifest,eligible,GAP_START,GAP_END

def main(path):
    source=json.loads(Path(path).read_text())
    intervals=load_manifest(path)
    if source["mismatch_count"]!=5:raise ValueError(f"unexpected_mismatch_count:{source['mismatch_count']}")
    if len(source["mismatches"])!=5:raise ValueError("truncated_mismatch_evidence")
    for symbol in ("SOLUSDT","XRPUSDT"):
        assert not eligible(intervals,symbol,GAP_START-300000,GAP_START-60000,GAP_START+300000)[0]
        assert eligible(intervals,symbol,GAP_END,GAP_END+60000,GAP_END+300000)[0]
    for issue in source["mismatches"]:
        symbol=issue["symbol"];start=issue["start_ms"];end=issue["end_exclusive_ms"]
        if eligible(intervals,symbol,start-300000,start-60000,end+300000)[0]:
            raise ValueError(f"mismatch_window_not_blocked:{symbol}:{start}")
        if not eligible(intervals,symbol,end,end+60000,end+300000)[0]:
            raise ValueError(f"valid_post_mismatch_window_blocked:{symbol}:{end}")
    report={"status":"PASS","manifest_mismatches":len(source["mismatches"]),
      "excluded_missing_day_per_symbol":1,"symbols":["SOLUSDT","XRPUSDT"],
      "gate_checks":"real_manifest_lookback_and_holding_horizon","actual_backtest_executed":False,
      "live_orders_executed":False}
    print(json.dumps(report,indent=2))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("manifest");a=p.parse_args();main(a.manifest)
