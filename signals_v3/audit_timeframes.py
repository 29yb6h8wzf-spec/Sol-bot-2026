"""Read-only cross-timeframe OHLCV audit for all acquired month/symbol pairs."""
import argparse,json
from pathlib import Path
from signals_v3.compare_kline_timeframes import compare

def audit(plan,root):
    root=Path(root).resolve()
    pairs=sorted({(r["symbol"],r["month"]) for r in plan["records"] if r["interval"]=="1m"})
    records=[]
    for symbol,month in pairs:
        if not symbol.endswith("USDT") or not symbol[:-4].isalnum():raise ValueError("invalid_symbol")
        if len(month)!=7 or month[4]!="-" or not month[:4].isdigit() or not month[5:].isdigit():raise ValueError("invalid_month")
        paths=[(root/symbol/interval/f"{symbol}-{interval}-{month}.zip").resolve() for interval in ("1m","5m")]
        if any(not p.is_relative_to(root) for p in paths):raise ValueError("unsafe_path")
        item={"symbol":symbol,"month":month}
        if not all(p.is_file() for p in paths):item.update(status="missing_archive")
        else:
            try:
                result=compare(*paths)
                item.update(result,status="consistent" if result["consistent"] else "mismatch")
            except (ValueError,OSError,EOFError) as exc:item.update(status="invalid",reason=str(exc))
        records.append(item)
    matched=sum(x["status"]=="consistent" for x in records)
    return {"pairs":len(records),"consistent_pairs":matched,"blocked_pairs":len(records)-matched,
            "all_pairs_consistent":bool(records) and matched==len(records),
            "dynamic_backtest_ready":False,"records":records}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("plan");p.add_argument("--root",required=True);p.add_argument("--output",required=True)
    a=p.parse_args();result=audit(json.loads(Path(a.plan).read_text()),a.root)
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:result[k] for k in ("pairs","consistent_pairs","blocked_pairs","all_pairs_consistent")}))
