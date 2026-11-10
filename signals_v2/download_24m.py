"""Public Binance USD-M monthly ZIP downloader. No keys, no orders."""
import argparse, hashlib, json, zipfile
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, urlopen

BASE = "https://data.binance.vision/data/futures/um/monthly"
def months(start,end):
    y,m=map(int,start.split("-")); ey,em=map(int,end.split("-"))
    while (y,m)<=(ey,em):
        yield f"{y:04d}-{m:02d}"
        y,m=(y+1,1) if m==12 else (y,m+1)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--start",default="2024-11")
    p.add_argument("--end",default="2026-10")
    p.add_argument("--output",default="research_data/monthly")
    a=p.parse_args()
    if a.start>a.end: raise ValueError("invalid_month_range")
    root=Path(a.output);root.mkdir(parents=True,exist_ok=True)
    records=[]; failures=[]
    for symbol in ("SOLUSDT","XRPUSDT"):
        for interval in ("1m","5m","fundingRate"):
            for month in months(a.start,a.end):
                name=f"{symbol}-{interval}-{month}.zip"
                folder=f"klines/{symbol}/{interval}" if interval!="fundingRate" else f"fundingRate/{symbol}"
                url=f"{BASE}/{folder}/{name}"
                path=root/name
                try:
                    if not path.exists():
                        req=Request(url,headers={"User-Agent":"SignalPilot-V2-public-research"})
                        with urlopen(req,timeout=90) as response, path.open("wb") as out:
                            while chunk:=response.read(1024*1024):out.write(chunk)
                    with zipfile.ZipFile(path) as z:
                        members=[m for m in z.infolist() if not m.is_dir()]
                        if len(members)!=1 or not members[0].filename.endswith(".csv") or members[0].file_size==0 or z.testzip() is not None:
                            raise ValueError("invalid_archive")
                    digest=hashlib.sha256(path.read_bytes()).hexdigest()
                    records.append({"symbol":symbol,"interval":interval,"month":month,"file":name,"sha256":digest,"bytes":path.stat().st_size,"source_url":url})
                    print("OK",name,flush=True)
                except Exception as exc:
                    path.unlink(missing_ok=True)
                    failures.append({"file":name,"error":str(exc)})
                    print("FAILED",name,str(exc),flush=True)
    manifest={"created_utc":datetime.now(timezone.utc).isoformat(),"status":"ZIP_ONLY" if not failures else "INCOMPLETE","files":records,"failures":failures,"note":"No candle continuity, funding alignment or profitability validation yet"}
    (root/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    if failures:raise SystemExit(1)
if __name__=="__main__":main()
