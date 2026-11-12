"""Fail-closed verification of offline Binance archive ZIP files.

Requires an already downloaded local archive. Never fetches remote data or
authorizes historical universe membership. Validates CSV timestamps, shape,
ZIP integrity and records SHA-256 for reproducibility.
"""
import argparse,csv,hashlib,json,zipfile
from pathlib import Path
from datetime import datetime,timezone

def verify_archive(path,interval,month):
    if interval not in ("1m","5m","fundingRate"):raise ValueError("invalid_interval")
    path=Path(path)
    if not path.is_file():raise ValueError("archive_missing")
    data=path.read_bytes()
    digest=hashlib.sha256(data).hexdigest()
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:raise ValueError("zip_crc_failure")
        names=[n for n in z.namelist() if n.lower().endswith(".csv") and not n.startswith("__MACOSX/")]
        if len(names)!=1:raise ValueError("expected_single_csv")
        count=0;min_ms=None;max_ms=None;last_ms=None
        with z.open(names[0]) as f:
            import io
            reader=csv.reader(io.TextIOWrapper(f,encoding="utf-8-sig",newline=""))
            for row in reader:
                if not row:continue
                try:timestamp=int(row[0])
                except ValueError:
                    if count==0 and row[0].lower() in ("open_time","open time","calc_time","calc time"):continue
                    raise ValueError("invalid_timestamp")
                if len(row)<2:raise ValueError("invalid_csv_shape")
                if last_ms is not None and timestamp<=last_ms:raise ValueError("non_monotonic_timestamps")
                last_ms=timestamp
                min_ms=timestamp if min_ms is None else min(min_ms,timestamp)
                max_ms=timestamp if max_ms is None else max(max_ms,timestamp)
                count+=1
    if not count:raise ValueError("empty_csv")
    start=int(datetime.strptime(month+"-01","%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()*1000)
    y,m=map(int,month.split("-"));next_y=y+(m==12);next_m=m%12+1
    end=int(datetime(next_y,next_m,1,tzinfo=timezone.utc).timestamp()*1000)
    if min_ms<start or max_ms>=end:raise ValueError("timestamp_outside_month")
    return {"path":str(path),"interval":interval,"month":month,"sha256":digest,
            "rows":count,"first_timestamp_ms":min_ms,"last_timestamp_ms":max_ms,
            "verified":True,"historical_universe_verified":False}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("path");p.add_argument("--interval",required=True)
    p.add_argument("--month",required=True);a=p.parse_args()
    print(json.dumps(verify_archive(a.path,a.interval,a.month),indent=2))
