"""Offline V3 archive audit: verify every locally present planned archive.

Does not download data or infer historical listings. Missing and invalid
archives remain blocked; verification results can feed archive inventory.
"""
import argparse,json
from pathlib import Path
from signals_v3.verify_archive import verify_archive

def audit_plan(plan,root):
    if not isinstance(plan,dict) or not isinstance(plan.get("records"),list):
        raise ValueError("invalid_archive_plan")
    root=Path(root).resolve()
    results=[];verified=0
    for row in plan["records"]:
        symbol=row["symbol"];month=row["month"];interval=row["interval"]
        if interval not in ("1m","5m","fundingRate") or not symbol.endswith("USDT") or not symbol[:-4].isalnum():
            raise ValueError("invalid_archive_plan_record")
        if interval=="fundingRate":filename=f"{symbol}-fundingRate-{month}.zip"
        else:filename=f"{symbol}-{interval}-{month}.zip"
        candidate=(root/symbol/interval/filename).resolve()
        if not candidate.is_relative_to(root):raise ValueError("unsafe_archive_path")
        record={"symbol":symbol,"month":month,"interval":interval,
                "path":str(candidate),"verified":False}
        if not candidate.is_file():record["reason"]="archive_missing"
        else:
            try:
                evidence=verify_archive(candidate,interval,month)
                record.update(evidence)
                verified+=1
            except (ValueError,OSError,KeyError,UnicodeError,EOFError) as exc:
                record["reason"]=type(exc).__name__+":"+str(exc)
        results.append(record)
    return {"research_only":True,"historical_universe_verified":False,
            "total":len(results),"verified":verified,"blocked":len(results)-verified,
            "ready_for_historical_dynamic_replay":False,"records":results}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("plan");p.add_argument("--root",required=True)
    p.add_argument("--output",required=True);a=p.parse_args()
    result=audit_plan(json.loads(Path(a.plan).read_text()),a.root)
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:result[k] for k in ("total","verified","blocked","ready_for_historical_dynamic_replay")}))
