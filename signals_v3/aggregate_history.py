"""Aggregate V3 monthly exploratory reports without promoting research to trading."""
import argparse,json
from pathlib import Path

MONTHS=[f"{y:04d}-{m:02d}" for y in (2024,2025,2026) for m in range(1,13)
        if "2024-11"<=f"{y:04d}-{m:02d}"<="2026-10"]

def aggregate(directory):
    root=Path(directory);summary={};monthly=[];total_trades=0;total_net=0.
    for month in MONTHS:
        matches=list(root.rglob(f"signals-v3-24m-{month}/v3_pilot_replay_report.json"))
        if len(matches)!=1:raise ValueError(f"missing_or_duplicate_month:{month}")
        report=json.loads(matches[0].read_text())
        if report.get("month")!=month or report.get("research_only") is not True or report.get("out_of_sample_certified") is not False:
            raise ValueError(f"invalid_research_report:{month}")
        for symbol in ("SOLUSDT","XRPUSDT"):
            record=report["symbols"][symbol]
            trades=record["trades"];net=record["net_r_total"]
            if trades!=sum(x["trades"] for x in record["strategies"].values()):
                raise ValueError(f"inconsistent_strategy_counts:{month}:{symbol}")
            if abs(net-sum(x["net_r_total"] for x in record["strategies"].values()))>1e-6:
                raise ValueError(f"inconsistent_strategy_returns:{month}:{symbol}")
            total_trades+=trades;total_net+=net
            entry=summary.setdefault(symbol,{"trades":0,"net_r_total":0.,"strategies":{}})
            entry["trades"]+=trades;entry["net_r_total"]+=net
            for name,detail in record["strategies"].items():
                s=entry["strategies"].setdefault(name,{"trades":0,"net_r_total":0.})
                s["trades"]+=detail["trades"];s["net_r_total"]+=detail["net_r_total"]
        monthly.append({"month":month,"trades":sum(x["trades"] for x in report["symbols"].values()),
                        "net_r_total":sum(x["net_r_total"] for x in report["symbols"].values())})
    for entry in summary.values():
        entry["mean_net_r"]=entry["net_r_total"]/entry["trades"] if entry["trades"] else None
        for s in entry["strategies"].values():
            s["mean_net_r"]=s["net_r_total"]/s["trades"] if s["trades"] else None
    return {"schema":"signals.v3.aggregate.1","research_only":True,
        "out_of_sample_certified":False,"profitability_proven":False,
        "months":len(monthly),"trades":total_trades,
        "net_r_total":total_net,"mean_net_r":total_net/total_trades if total_trades else None,
        "symbols":summary,"monthly":monthly,
        "warning":"exploratory only; same-period model comparison does not establish OOS edge"}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("directory");p.add_argument("output")
    args=p.parse_args();result=aggregate(args.directory)
    Path(args.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
