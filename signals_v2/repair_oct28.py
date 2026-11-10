"""Repair a known missing UTC day from official Binance daily futures archives.

Preserves the original monthly ZIP in a separate input directory. Fail closed
unless exactly the expected day is missing and the daily archive is contiguous.
"""
import argparse,csv,io,zipfile,hashlib,json
from pathlib import Path
from urllib.request import Request,urlopen

DAY="2026-10-28"
BASE="https://data.binance.vision/data/futures/um/daily/klines"
STEPS={"1m":60000,"5m":300000}
DAY_START=1793145600000
DAY_END=1793232000000

def normalize(rows):
    result=[]
    for row in rows:
        if not row or not row[0].strip().isdigit():continue
        t=int(row[0])
        if t>=100_000_000_000_000:
            if t%1000:raise ValueError("submillisecond_timestamp")
            t//=1000
        result.append((t,row))
    return result

def load_csv_zip(path):
    with zipfile.ZipFile(path) as z:
        names=[n for n in z.namelist() if n.endswith(".csv")]
        if len(names)!=1 or z.testzip() is not None:raise ValueError("bad_zip")
        return normalize(list(csv.reader(io.TextIOWrapper(z.open(names[0]),encoding="utf-8-sig"))))

def repair(source,target,fetch=urlopen):
    source,target=Path(source),Path(target)
    target.mkdir(parents=True,exist_ok=True)
    receipts=[]
    for symbol in ("SOLUSDT","XRPUSDT"):
        for interval,step in STEPS.items():
            name=f"{symbol}-{interval}-2026-10.zip"
            original=source/name
            existing=load_csv_zip(original)
            expected=DAY_START
            before=[r for t,r in existing if t<DAY_START]
            after=[r for t,r in existing if t>=DAY_END]
            inside=[r for t,r in existing if DAY_START<=t<DAY_END]
            if inside:raise ValueError("not_an_exact_missing_day")
            if int(before[-1][0])!=DAY_START-step or int(after[0][0])!=DAY_END:
                raise ValueError("wrong_gap_boundaries")
            daily_name=f"{symbol}-{interval}-{DAY}.zip"
            url=f"{BASE}/{symbol}/{interval}/{daily_name}"
            with fetch(Request(url,headers={"User-Agent":"SignalPilot-V2-research"}),timeout=90) as response:
                daily_bytes=response.read()
            daily_path=target/daily_name
            daily_path.write_bytes(daily_bytes)
            daily=load_csv_zip(daily_path)
            if len(daily)!=86400000//step or any(t!=expected+i*step for i,(t,_) in enumerate(daily)):
                raise ValueError("daily_not_contiguous")
            merged=before+[row for _,row in daily]+after
            if len(merged)!=len(existing)+len(daily):raise ValueError("unexpected_count")
            output=target/name
            with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
                buf=io.StringIO();writer=csv.writer(buf,lineterminator="\n");writer.writerows(merged)
                z.writestr(name.replace(".zip",".csv"),buf.getvalue())
            receipts.append({"symbol":symbol,"interval":interval,"missing_day":DAY,
              "source_daily_url":url,"source_daily_sha256":hashlib.sha256(daily_bytes).hexdigest(),
              "original_monthly_sha256":hashlib.sha256(original.read_bytes()).hexdigest(),
              "repaired_monthly_sha256":hashlib.sha256(output.read_bytes()).hexdigest(),
              "restored_rows":len(daily)})
    (target/"repair_receipts.json").write_text(json.dumps(receipts,indent=2)+"\n")
    return receipts

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",required=True);p.add_argument("--output",required=True)
    a=p.parse_args()
    print(json.dumps(repair(a.source,a.output),indent=2))
