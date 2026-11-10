"""Fail-closed OHLCV sanity checks for historical kline archives.

This complements timestamp continuity and 1m/5m aggregation checks.
"""
import argparse,csv,io,json,zipfile
from decimal import Decimal,InvalidOperation
from pathlib import Path

def audit_ohlcv(path,limit_examples=10):
    rows=0;invalid=0;examples=[]
    with zipfile.ZipFile(Path(path)) as z:
        names=[n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(names)!=1:raise ValueError("expected_single_csv")
        with z.open(names[0]) as raw:
            for row in csv.reader(io.TextIOWrapper(raw,encoding="utf-8-sig")):
                if not row:continue
                try:timestamp=int(row[0])
                except ValueError:
                    if rows==0 and row[0].strip().lower() in ("open_time","open time"):continue
                    raise ValueError("invalid_timestamp")
                rows+=1
                try:
                    if len(row)<6:raise ValueError("missing_ohlcv_columns")
                    o,h,l,c,v=(Decimal(x) for x in row[1:6])
                    if not all(x.is_finite() for x in (o,h,l,c,v)):raise ValueError("nonfinite")
                    if min(o,h,l,c)<=0 or v<0 or h<max(o,c,l) or l>min(o,c,h):
                        raise ValueError("invalid_ohlcv")
                except (InvalidOperation,ValueError) as exc:
                    invalid+=1
                    if len(examples)<limit_examples:examples.append({"timestamp_ms":timestamp,"reason":str(exc)})
    return {"rows":rows,"invalid_rows":invalid,"valid":rows>0 and invalid==0,"examples":examples}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("archive");a=p.parse_args()
    print(json.dumps(audit_ohlcv(a.archive)))
