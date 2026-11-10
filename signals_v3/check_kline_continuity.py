"""Strict OHLCV timestamp continuity check for verified monthly kline archives.

Read-only; funding schedules are variable and intentionally excluded.
"""
import argparse,csv,io,json,zipfile
from calendar import monthrange
from datetime import datetime,timezone
from pathlib import Path

def check_kline_continuity(path,interval,month):
    if interval not in ("1m","5m"):raise ValueError("kline_interval_required")
    step=60_000 if interval=="1m" else 300_000
    year,m=map(int,month.split("-"))
    start=int(datetime(year,m,1,tzinfo=timezone.utc).timestamp()*1000)
    expected=monthrange(year,m)[1]*86_400_000//step
    last=None;rows=0;gaps=0;duplicates=0;off_grid=0
    with zipfile.ZipFile(Path(path)) as archive:
        names=[n for n in archive.namelist() if n.lower().endswith(".csv")]
        if len(names)!=1:raise ValueError("expected_single_csv")
        with archive.open(names[0]) as raw:
            reader=csv.reader(io.TextIOWrapper(raw,encoding="utf-8-sig"))
            for row in reader:
                if not row:continue
                try:t=int(row[0])
                except ValueError:
                    if rows==0 and row[0].lower() in ("open_time","open time"):continue
                    raise ValueError("invalid_timestamp")
                if (t-start)%step:off_grid+=1
                if last is not None:
                    if t<=last:duplicates+=1
                    elif t-last>step:gaps+=(t-last)//step-1
                last=t;rows+=1
    complete=(rows==expected and gaps==0 and duplicates==0 and off_grid==0
              and last==start+(expected-1)*step)
    return {"interval":interval,"month":month,"rows":rows,"expected_rows":expected,
            "missing_intervals":gaps,"non_increasing":duplicates,
            "off_grid":off_grid,"continuous":complete}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("path");p.add_argument("--interval",required=True)
    p.add_argument("--month",required=True);a=p.parse_args()
    print(json.dumps(check_kline_continuity(a.path,a.interval,a.month)))
