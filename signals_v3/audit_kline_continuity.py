"""Audit every local monthly kline ZIP for missing, duplicate or off-grid bars.

Funding-rate ZIPs are reported as not applicable. Research-only.
"""
import argparse,json
from pathlib import Path
from signals_v3.check_kline_continuity import check_kline_continuity

def audit_continuity(plan,root):
    root=Path(root).resolve();records=[]
    for row in plan["records"]:
        symbol,month,interval=row["symbol"],row["month"],row["interval"]
        if interval not in ("1m","5m"):
            records.append({"symbol":symbol,"month":month,"interval":interval,"status":"not_applicable"})
            continue
        if not symbol.endswith("USDT") or not symbol[:-4].isalnum():
            raise ValueError("invalid_symbol")
        if not (len(month)==7 and month[4]=="-" and month[:4].isdigit() and month[5:].isdigit()):
            raise ValueError("invalid_month")
        path=(root/symbol/interval/f"{symbol}-{interval}-{month}.zip").resolve()
        if not path.is_relative_to(root):raise ValueError("unsafe_archive_path")
        record={"symbol":symbol,"month":month,"interval":interval}
        if not path.is_file():record.update(status="missing")
        else:
            try:
                metrics=check_kline_continuity(path,interval,month)
                record.update(metrics,status="continuous" if metrics["continuous"] else "gaps_or_invalid")
            except (ValueError,OSError,EOFError) as exc:
                record.update(status="invalid",reason=str(exc))
        records.append(record)
    klines=[r for r in records if r["interval"] in ("1m","5m")]
    continuous=sum(r["status"]=="continuous" for r in klines)
    return {"total_kline_archives":len(klines),"continuous":continuous,
            "blocked":len(klines)-continuous,"all_klines_continuous":bool(klines) and continuous==len(klines),
            "historical_universe_verified":False,"dynamic_backtest_ready":False,"records":records}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("plan");p.add_argument("--root",required=True)
    p.add_argument("--output",required=True);a=p.parse_args()
    result=audit_continuity(json.loads(Path(a.plan).read_text()),a.root)
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:result[k] for k in ("total_kline_archives","continuous","blocked","all_klines_continuous")}))
