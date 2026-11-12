"""Opt-in, read-only acquisition of public Binance monthly archive ZIPs.

Never connects to trading APIs, never follows redirects to other hosts, and
never treats a downloaded archive as historical universe evidence.
"""
import argparse,json,urllib.request,urllib.error
from pathlib import Path
from urllib.parse import urlparse
from signals_v3.archive_acquisition_plan import archive_url
from signals_v3.verify_archive import verify_archive

MAX_BYTES=250_000_000

class SameHostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if urlparse(newurl).scheme!="https" or urlparse(newurl).hostname!="data.binance.vision":
            raise ValueError("redirect_not_allowed")
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def acquire(plan,root,max_files=1):
    root=Path(root).resolve();opener=urllib.request.build_opener(SameHostRedirect)
    results=[];attempted=0
    for record in plan["records"]:
        symbol,month,interval=record["symbol"],record["month"],record["interval"]
        url=archive_url(symbol,month,interval)
        if record.get("candidate_url")!=url:raise ValueError("untrusted_archive_url")
        target=(root/symbol/interval/url.rsplit("/",1)[-1]).resolve()
        if not target.is_relative_to(root):raise ValueError("unsafe_path")
        if target.is_file():
            results.append({"symbol":symbol,"month":month,"interval":interval,"status":"already_present"})
            continue
        if attempted>=max_files:break
        attempted+=1;target.parent.mkdir(parents=True,exist_ok=True)
        temp=target.with_suffix(".part")
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"SignalPilot-V3-Research/1.0"})
            with opener.open(req,timeout=25) as response,temp.open("wb") as out:
                if response.status!=200:raise ValueError("unexpected_http_status")
                size=0
                while True:
                    chunk=response.read(1024*1024)
                    if not chunk:break
                    size+=len(chunk)
                    if size>MAX_BYTES:raise ValueError("archive_too_large")
                    out.write(chunk)
            evidence=verify_archive(temp,interval,month)
            temp.replace(target)
            results.append({"symbol":symbol,"month":month,"interval":interval,"status":"verified_download","sha256":evidence["sha256"],"rows":evidence["rows"]})
        except (urllib.error.URLError,OSError,ValueError,EOFError) as exc:
            results.append({"symbol":symbol,"month":month,"interval":interval,"status":"blocked","reason":str(exc)})
        finally:
            temp.unlink(missing_ok=True)
    return {"attempted":attempted,"results":results,"historical_universe_verified":False,"dynamic_backtest_ready":False}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("plan");p.add_argument("--root",required=True)
    p.add_argument("--max-files",type=int,default=1);p.add_argument("--output",required=True);a=p.parse_args()
    if not 1<=a.max_files<=12:raise ValueError("max_files_out_of_range")
    result=acquire(json.loads(Path(a.plan).read_text()),a.root,a.max_files)
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result))
