"""Generate exact exclusion windows for known cross-timeframe discrepancies.

No candle values are changed. All candidate windows that touch a mismatch
are excluded from backtests until independent data reconciliation.
"""
import json
from datetime import datetime,timezone,timedelta
from pathlib import Path
from quality_gate import validate

def build_report(root):
    result=validate(root)
    windows=[]
    for error in result["errors"]:
        reason=error["reason"]
        if not reason.startswith("ohlcv_mismatch:"):
            continue
        _,ts,*_=reason.split(":")
        start=int(ts)
        windows.append({"symbol":error["symbol"],"month":error["month"],
          "start_ms":start,"end_exclusive_ms":start+300000,
          "start_utc":datetime.fromtimestamp(start/1000,timezone.utc).isoformat(),
          "reason":reason,"policy":"exclude_5m_and_all_overlapping_trade_windows"})
    return {"status":"EXCLUSIONS_REQUIRED" if windows else "NO_OHLCV_MISMATCHES",
      "source_quality_gate_status":result["status"],"verified_symbol_months":result["months_verified"],
      "excluded_5m_windows":windows,"limitations":["Only first mismatch per failing symbol-month is identified; full mismatch enumeration required before backtesting","Funding schema-specific validation remains open","Known missing 2026-10-28 UTC day must also be excluded"]}
if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("directory");a=p.parse_args()
    root=Path(a.directory);r=build_report(root)
    (root/"mismatch_exclusions.json").write_text(json.dumps(r,indent=2)+"\n")
    print(json.dumps(r,indent=2))
