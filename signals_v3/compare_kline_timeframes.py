"""Compare archived 5m OHLCV candles to aggregated 1m candles, offline."""
import argparse,csv,io,json,zipfile
from decimal import Decimal
from pathlib import Path

def read_candles(path):
    with zipfile.ZipFile(path) as z:
        names=[n for n in z.namelist() if n.endswith(".csv")]
        if len(names)!=1:raise ValueError("expected_single_csv")
        with z.open(names[0]) as raw:
            for row in csv.reader(io.TextIOWrapper(raw,encoding="utf-8-sig")):
                if not row:continue
                try:t=int(row[0])
                except ValueError:
                    if row[0].lower() in ("open_time","open time"):continue
                    raise
                if len(row)<6:raise ValueError("missing_ohlcv_columns")
                yield t,tuple(Decimal(v) for v in row[1:6])

def compare(archive_1m,archive_5m,limit_examples=10):
    groups={};invalid=0
    for t,(o,h,l,c,v) in read_candles(archive_1m):
        bucket=t//300000*300000
        if bucket not in groups:groups[bucket]=[]
        groups[bucket].append((t,o,h,l,c,v))
    checked=0;mismatches=0;examples=[]
    for t,(o,h,l,c,v) in read_candles(archive_5m):
        bars=groups.get(t,[])
        if len(bars)!=5 or [x[0] for x in bars]!=[t+i*60000 for i in range(5)]:
            mismatches+=1
            if len(examples)<limit_examples:examples.append({"time_ms":t,"reason":"missing_or_misaligned_1m"})
            continue
        actual=(bars[0][1],max(x[2] for x in bars),min(x[3] for x in bars),
                bars[-1][4],sum((x[5] for x in bars),Decimal(0)))
        if actual!=(o,h,l,c,v):
            mismatches+=1
            if len(examples)<limit_examples:examples.append({"time_ms":t,"reason":"ohlcv_mismatch"})
        else:checked+=1
    return {"checked":checked,"mismatches":mismatches,"matching":checked,
            "consistent":checked>0 and mismatches==0,"examples":examples,
            "research_only":True}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("archive_1m");p.add_argument("archive_5m")
    a=p.parse_args();print(json.dumps(compare(a.archive_1m,a.archive_5m)))
