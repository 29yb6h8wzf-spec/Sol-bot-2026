"""Independent, fail-closed market-history audit with explicit UTC gap exclusion.

A missing day is NEVER filled with synthetic candles. The four October archives
are accepted only when their sole gap is exactly 2026-10-28 UTC.
"""
import csv,io,json,zipfile,hashlib,calendar,datetime
from pathlib import Path

SYMBOLS=("SOLUSDT","XRPUSDT")
INTERVALS={"1m":60000,"5m":300000}
GAP_START=1793145600000
GAP_END=1793232000000
def months():
    for year in (2024,2025,2026):
        for month in range(1,13):
            if (2024,11)<=(year,month)<=(2026,10):
                yield year,month
def ms(y,m):
    return calendar.timegm(datetime.datetime(y,m,1).timetuple())*1000
def inspect(path,interval,year,month):
    step=INTERVALS.get(interval)
    with zipfile.ZipFile(path) as z:
        names=[n for n in z.namelist() if n.endswith(".csv")]
        if len(names)!=1 or z.testzip() is not None:raise ValueError("invalid_zip")
        count=0;last=None;first=None;gaps=[]
        with z.open(names[0]) as fh:
            for row in csv.reader(io.TextIOWrapper(fh,encoding="utf-8-sig")):
                if not row or not row[0].isdigit():continue
                raw=int(row[0]);t=raw//1000 if raw>=100000000000000 else raw
                if raw>=100000000000000 and raw%1000:raise ValueError("submillisecond_timestamp")
                if first is None:first=t
                if last is not None:
                    if step and t-last!=step:
                        gaps.append({"after":last,"before":t,"missing_candles":(t-last)//step-1})
                    elif not step and t<=last:raise ValueError("funding_not_monotonic")
                if step:
                    if len(row)<6:raise ValueError("bad_columns")
                    o,h,l,c,v=map(float,row[1:6])
                    import math
                    if not all(map(math.isfinite,(o,h,l,c,v))) or not (0<l<=min(o,c)<=max(o,c)<=h) or v<0:raise ValueError("invalid_ohlcv")
                last=t;count+=1
        if count==0:raise ValueError("empty_archive")
        start=ms(year,month)
        end=ms(year+1,1) if month==12 else ms(year,month+1)
        if not start<=first<=last<end:raise ValueError("out_of_month")
        if step and (first!=start or last!=end-step):raise ValueError("month_boundary_missing")
        if step:
            expected=(end-start)//step
            if count+sum(g["missing_candles"] for g in gaps)!=expected:raise ValueError("unexpected_row_count")
        return {"rows":count,"gaps":gaps,"first":first,"last":last}

def audit(root):
    root=Path(root);items=[];errors=[];exclusions=[]
    for symbol in SYMBOLS:
        for interval in ("1m","5m","fundingRate"):
            previous=None
            for y,m in months():
                name=f"{symbol}-{interval}-{y:04d}-{m:02d}.zip"
                try:
                    path=root/name
                    if not path.is_file():raise ValueError("missing_file")
                    result=inspect(path,interval,y,m)
                    step=INTERVALS.get(interval)
                    if step and previous is not None and result["first"]-previous!=step:
                        raise ValueError("cross_month_gap")
                    if step:previous=result["last"]
                    gaps=result.pop("gaps")
                    if gaps:
                        if (y,m)!=(2026,10) or len(gaps)!=1 or not step or gaps[0]["after"]!=GAP_START-step or gaps[0]["before"]!=GAP_END:
                            raise ValueError(f"unapproved_gap:{gaps}")
                        exclusions.append({"symbol":symbol,"interval":interval,"start_utc":"2026-10-28T00:00:00Z","end_exclusive_utc":"2026-10-29T00:00:00Z","missing_candles":gaps[0]["missing_candles"],"policy":"exclude_from_backtest"})
                    items.append({"file":name,**result,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
                except Exception as e:errors.append({"file":name,"reason":str(e)})
    status="PASS_WITH_EXCLUSIONS" if not errors and len(items)==144 and len(exclusions)==4 else "FAIL"
    return {"status":status,"archives_inspected":len(items),"expected":144,"continuous_archives":len(items)-len(exclusions),"segmented_archives":len(exclusions),"exclusions":exclusions,"errors":errors,"funding_content_validated":False,"cross_timeframe_reconciliation_validated":False,"profitability_proven":False,"items":items}
if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("directory");args=p.parse_args()
    report=audit(args.directory)
    out=Path(args.directory)/"segmented_audit_report.json"
    out.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k!="items"},indent=2))
    if report["status"]!="PASS_WITH_EXCLUSIONS":raise SystemExit(1)
