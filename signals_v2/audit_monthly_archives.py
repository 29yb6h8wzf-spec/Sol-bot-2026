"""Audit downloaded Binance monthly ZIP archives without loading candles into memory."""
import argparse,csv,hashlib,io,json,zipfile
from pathlib import Path
from datetime import datetime,timezone
STEPS={"1m":60000,"5m":300000}
SYMBOLS=("SOLUSDT","XRPUSDT")
def months(start,end):
    y,m=map(int,start.split("-"));ey,em=map(int,end.split("-"))
    while (y,m)<=(ey,em):
        yield f"{y:04d}-{m:02d}"
        y,m=(y+1,1) if m==12 else (y,m+1)
def timestamp(s):
    return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()*1000)
def audit(root,start="2024-11",end="2026-10"):
    root=Path(root);results=[];errors=[]
    for symbol in SYMBOLS:
        for interval in (*STEPS,"fundingRate"):
            prev=None;total=0
            for month in months(start,end):
                name=f"{symbol}-{interval}-{month}.zip";p=root/name
                try:
                    if not p.is_file():raise ValueError("missing_archive")
                    with zipfile.ZipFile(p) as z:
                        names=[n for n in z.namelist() if n.endswith(".csv")]
                        if len(names)!=1 or z.testzip() is not None:raise ValueError("bad_zip")
                        with z.open(names[0]) as f:
                            reader=csv.reader(io.TextIOWrapper(f,encoding="utf-8-sig"))
                            first=None;last=None;count=0
                            month_start=timestamp(month+"-01")
                            year,mo=map(int,month.split("-"))
                            next_month=f"{year+1:04d}-01" if mo==12 else f"{year:04d}-{mo+1:02d}"
                            month_end=timestamp(next_month+"-01")
                            for row in reader:
                                if not row or not row[0].strip().isdigit():continue
                                raw_t=int(row[0])
                                t=raw_t//1000 if raw_t>=100_000_000_000_000 else raw_t
                                if raw_t>=100_000_000_000_000 and raw_t%1000!=0:raise ValueError(f"submillisecond_timestamp:{raw_t}")
                                if not month_start<=t<month_end:raise ValueError("outside_month")
                                if interval in STEPS:
                                    step=STEPS[interval]
                                    if first is None and t!=month_start:raise ValueError("missing_month_start")
                                    if last is not None and t-last!=step:raise ValueError(f"gap_or_duplicate:prev={last}:current={t}:delta={t-last}:expected={step}")
                                    if len(row)<6:raise ValueError("short_ohlcv")
                                    import math
                                    o,h,l,c,v=map(float,row[1:6])
                                    if not all(map(math.isfinite,(o,h,l,c,v))) or not (0<l<=min(o,c)<=max(o,c)<=h) or v<0:raise ValueError("bad_ohlcv")
                                elif last is not None and t<=last:raise ValueError(f"funding_not_monotonic:prev={last}:current={t}")
                                if first is None:first=t
                                last=t;count+=1
                            if not count:raise ValueError("empty_csv")
                            if interval in STEPS and last!=month_end-STEPS[interval]:raise ValueError("missing_month_end")
                            if interval in STEPS and prev is not None and first-prev!=STEPS[interval]:raise ValueError("cross_month_gap")
                            if interval in STEPS:prev=last
                            total+=count
                            results.append({"symbol":symbol,"interval":interval,"month":month,"rows":count,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()})
                except Exception as exc:
                    errors.append({"file":name,"reason":str(exc)})
    expected=24*2*3
    if len(results)!=expected:errors.append({"reason":"archive_count","expected":expected,"actual":len(results)})
    return {"status":"PASS" if not errors else "FAIL","archives_verified":len(results),"expected_archives":expected,"errors":errors,"results":results,"funding_timestamps_only":True,"oos_validated":False,"profitability_proven":False}
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("directory");a=p.parse_args()
    report=audit(a.directory)
    out=Path(a.directory)/"integrity_report.json";out.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k!="results"},indent=2))
    if report["status"]!="PASS":raise SystemExit(1)
