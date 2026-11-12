"""Strict funding-rate schema and value audit, with explicit fail-closed reporting."""
import argparse,csv,io,json,math,zipfile
from pathlib import Path
from audit_segmented_history import months,ms

def audit(root):
    root=Path(root);reports=[];errors=[]
    for symbol in ("SOLUSDT","XRPUSDT"):
        previous=None
        for year,month in months():
            name=f"{symbol}-fundingRate-{year:04d}-{month:02d}.zip"
            try:
                with zipfile.ZipFile(root/name) as z:
                    names=[n for n in z.namelist() if n.endswith(".csv")]
                    if len(names)!=1 or z.testzip() is not None:raise ValueError("invalid_zip")
                    with z.open(names[0]) as f:
                        rows=csv.reader(io.TextIOWrapper(f,encoding="utf-8-sig"))
                        count=0;rates=[];widths=set()
                        for row in rows:
                            if not row:continue
                            if not row[0].strip().isdigit():
                                if count==0:continue
                                raise ValueError("unexpected_header")
                            widths.add(len(row))
                            raw=int(row[0]);t=raw//1000 if raw>=100000000000000 else raw
                            if raw>=100000000000000 and raw%1000:raise ValueError("submillisecond_timestamp")
                            start=ms(year,month)
                            end=ms(year+1,1) if month==12 else ms(year,month+1)
                            if not start<=t<end:raise ValueError("timestamp_outside_month")
                            if previous is not None and t<=previous:raise ValueError("non_monotonic_or_duplicate")
                            if len(row)<3:raise ValueError("unexpected_funding_schema")
                            # Binance Vision fundingRate archives use calc_time, funding_interval_hours, last_funding_rate.
                            interval=float(row[1]);rate=float(row[2])
                            if not math.isfinite(interval) or not math.isfinite(rate):raise ValueError("nonfinite")
                            if not 0<interval<=24:raise ValueError(f"invalid_funding_interval:{interval}")
                            if abs(rate)>0.1:raise ValueError(f"implausible_funding_rate:{rate}")
                            previous=t;count+=1;rates.append(rate)
                        if not count:raise ValueError("empty_funding")
                        if widths!={3}:raise ValueError(f"unexpected_column_counts:{sorted(widths)}")
                        reports.append({"symbol":symbol,"month":f"{year:04d}-{month:02d}","rows":count,"min_rate":min(rates),"max_rate":max(rates)})
            except Exception as e:errors.append({"file":name,"error":str(e)})
    return {"status":"PASS" if not errors and len(reports)==48 else "FAIL","funding_months_verified":len(reports),"expected":48,"errors":errors,"results":reports,"profitability_proven":False}
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("directory");a=p.parse_args()
    root=Path(a.directory);r=audit(root)
    (root/"funding_schema_report.json").write_text(json.dumps(r,indent=2)+"\n")
    print(json.dumps({k:v for k,v in r.items() if k!="results"},indent=2))
    if r["status"]!="PASS":raise SystemExit(1)
