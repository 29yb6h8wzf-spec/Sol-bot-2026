"""Aggregate funding archive validation for research evidence."""
import argparse,json
from pathlib import Path
from signals_v3.audit_funding_rates import audit_funding

def run(plan,root):
    root=Path(root).resolve();results=[]
    for r in plan["records"]:
        if r["interval"]!="fundingRate":continue
        symbol,month=r["symbol"],r["month"]
        if not symbol.endswith("USDT") or not symbol[:-4].isalnum():raise ValueError("invalid_symbol")
        path=(root/symbol/"fundingRate"/f"{symbol}-fundingRate-{month}.zip").resolve()
        if not path.is_relative_to(root):raise ValueError("unsafe_path")
        item={"symbol":symbol,"month":month}
        if not path.is_file():item["status"]="missing"
        else:
            try:
                result=audit_funding(path,month)
                item.update(result,status="valid" if result["valid"] else "invalid")
            except (ValueError,OSError,EOFError) as exc:item.update(status="invalid",reason=str(exc))
        results.append(item)
    good=sum(r["status"]=="valid" for r in results)
    return {"funding_archives":len(results),"valid_archives":good,
            "blocked_archives":len(results)-good,
            "funding_schedule_verified":False,"dynamic_backtest_ready":False,"records":results}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("plan");p.add_argument("--root",required=True);p.add_argument("--output",required=True)
    a=p.parse_args();result=run(json.loads(Path(a.plan).read_text()),a.root)
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:result[k] for k in ("funding_archives","valid_archives","blocked_archives")}))
