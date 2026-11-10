"""Batch OHLCV sanity audit for every 1m/5m research archive."""
import argparse,json
from pathlib import Path
from signals_v3.audit_ohlcv_values import audit_ohlcv

def run(plan,root):
    root=Path(root).resolve();results=[]
    for item in plan["records"]:
        if item["interval"] not in ("1m","5m"):continue
        symbol,month,interval=(item[k] for k in ("symbol","month","interval"))
        if not symbol.endswith("USDT") or not symbol[:-4].isalnum():raise ValueError("invalid_symbol")
        path=(root/symbol/interval/f"{symbol}-{interval}-{month}.zip").resolve()
        if not path.is_relative_to(root):raise ValueError("unsafe_path")
        record={"symbol":symbol,"month":month,"interval":interval}
        if not path.is_file():record["status"]="missing"
        else:
            try:
                result=audit_ohlcv(path)
                record.update(result,status="valid" if result["valid"] else "invalid")
            except (ValueError,OSError,EOFError) as exc:record.update(status="invalid",reason=str(exc))
        results.append(record)
    good=sum(r["status"]=="valid" for r in results)
    return {"kline_archives":len(results),"valid_archives":good,"blocked_archives":len(results)-good,
            "all_ohlcv_valid":bool(results) and good==len(results),"dynamic_backtest_ready":False,
            "records":results}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("plan");p.add_argument("--root",required=True);p.add_argument("--output",required=True)
    a=p.parse_args();result=run(json.loads(Path(a.plan).read_text()),a.root)
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:result[k] for k in ("kline_archives","valid_archives","blocked_archives","all_ohlcv_valid")}))
