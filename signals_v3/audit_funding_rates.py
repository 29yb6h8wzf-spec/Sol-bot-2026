"""Offline funding-rate archive audit; fail closed on malformed records."""
import argparse,csv,io,json,zipfile
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
from pathlib import Path

def audit_funding(path,month):
    year,m=map(int,month.split("-"))
    start=int(datetime(year,m,1,tzinfo=timezone.utc).timestamp()*1000)
    end=int(datetime(year+1,1,1,tzinfo=timezone.utc).timestamp()*1000) if m==12 else int(datetime(year,m+1,1,tzinfo=timezone.utc).timestamp()*1000)
    count=0;previous=None;duplicates=0;out_of_month=0;invalid_rates=0
    with zipfile.ZipFile(path) as z:
        names=[n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(names)!=1:raise ValueError("expected_single_csv")
        with z.open(names[0]) as raw:
            for row in csv.reader(io.TextIOWrapper(raw,encoding="utf-8-sig")):
                if not row:continue
                try:t=int(row[0])
                except ValueError:
                    if count==0 and row[0].lower().strip() in ("calc_time","calc time","fundingtime","funding_time"):continue
                    raise ValueError("invalid_funding_timestamp")
                if len(row)<2:raise ValueError("missing_funding_rate")
                try:
                    rate=Decimal(row[1])
                    if not rate.is_finite():invalid_rates+=1
                except InvalidOperation:invalid_rates+=1
                if previous is not None and t<=previous:duplicates+=1
                if not start<=t<end:out_of_month+=1
                previous=t;count+=1
    return {"month":month,"rows":count,"duplicate_or_nonmonotonic":duplicates,
            "outside_month":out_of_month,"invalid_rates":invalid_rates,
            "valid":count>0 and duplicates==0 and out_of_month==0 and invalid_rates==0,
            "schedule_completeness_verified":False}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("archive");p.add_argument("--month",required=True)
    a=p.parse_args();print(json.dumps(audit_funding(a.archive,a.month)))
