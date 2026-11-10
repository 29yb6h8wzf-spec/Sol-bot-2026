"""Enumerate every 1m-vs-5m OHLCV mismatch; never rewrite market prices."""
import csv,io,json,math,zipfile,calendar,datetime
from pathlib import Path
from audit_segmented_history import months,GAP_START,GAP_END

def iter_rows(path):
    with zipfile.ZipFile(path) as z:
        names=[n for n in z.namelist() if n.endswith(".csv")]
        if len(names)!=1 or z.testzip() is not None:raise ValueError("invalid_zip")
        with z.open(names[0]) as f:
            for row in csv.reader(io.TextIOWrapper(f,encoding="utf-8-sig")):
                if row and row[0].strip().isdigit():
                    raw=int(row[0]);yield (raw//1000 if raw>=100000000000000 else raw),row

def scan(root):
    root=Path(root);issues=[];summary=[];fatal=[]
    for symbol in ("SOLUSDT","XRPUSDT"):
        for y,m in months():
            month=f"{y:04d}-{m:02d}"
            try:
                minute=iter_rows(root/f"{symbol}-1m-{month}.zip")
                five=iter_rows(root/f"{symbol}-5m-{month}.zip")
                current=next(five,None);group=[];checked=0
                for t,r in minute:
                    group.append((t,r))
                    if len(group)<5:continue
                    if current is None:raise ValueError("five_minute_archive_shorter")
                    ft,fr=current
                    if len(group)!=5 or ft!=group[0][0] or any(group[i][0]!=ft+i*60000 for i in range(5)):
                        raise ValueError(f"time_alignment_error:{ft}")
                    a=[[float(v[1][i]) for i in (1,2,3,4,5)] for v in group]
                    expected=[a[0][0],max(v[1] for v in a),min(v[2] for v in a),a[-1][3],sum(v[4] for v in a)]
                    actual=[float(fr[i]) for i in (1,2,3,4,5)]
                    fields=("open","high","low","close","volume")
                    different=[{"field":field,"monthly_5m":x,"aggregated_1m":v} for field,x,v in zip(fields,actual,expected) if not math.isclose(x,v,rel_tol=1e-8,abs_tol=1e-7)]
                    if different:issues.append({"symbol":symbol,"month":month,"start_ms":ft,"end_exclusive_ms":ft+300000,"differences":different,"policy":"exclude_overlapping_backtest_windows"})
                    checked+=1;group=[];current=next(five,None)
                if group or current is not None:raise ValueError("partial_or_extra_candles")
                summary.append({"symbol":symbol,"month":month,"compared_5m":checked})
            except Exception as e:fatal.append({"symbol":symbol,"month":month,"error":str(e)})
    return {"status":"PASS_WITH_EXCLUSIONS" if not fatal and len(summary)==48 else "FAIL",
      "months_scanned":len(summary),"mismatch_count":len(issues),"mismatches":issues,
      "fatal_errors":fatal,"known_missing_day":"2026-10-28 UTC","funding_schema_validated":False}
if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("directory");a=p.parse_args()
    root=Path(a.directory);r=scan(root)
    (root/"all_ohlcv_mismatches.json").write_text(json.dumps(r,indent=2)+"\n")
    print(json.dumps({k:v for k,v in r.items() if k!="mismatches"},indent=2))
    if r["status"]!="PASS_WITH_EXCLUSIONS":raise SystemExit(1)
