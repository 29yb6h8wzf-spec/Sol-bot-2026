"""Fail-closed exploratory V3 diagnostic, not a strategy promotion gate."""
import json
from pathlib import Path

def diagnose(report):
    if report.get("out_of_sample_certified") is not False or report.get("research_only") is not True:
        raise ValueError("untrusted_research_report")
    total=0;net=0.;strategies={}
    for symbol,record in report.get("symbols",{}).items():
        n=record["trades"];value=record["net_r_total"]
        if n<0 or not isinstance(value,(float,int)) or n!=sum(s["trades"] for s in record["strategies"].values()):
            raise ValueError("inconsistent_trade_totals")
        total+=n;net+=value
        for name,s in record["strategies"].items():
            entry=strategies.setdefault(name,{"trades":0,"net_r_total":0.})
            entry["trades"]+=s["trades"];entry["net_r_total"]+=s["net_r_total"]
    if total<1:raise ValueError("no_trades")
    for record in strategies.values():
        record["mean_net_r"]=record["net_r_total"]/record["trades"]
        record["insufficient_sample"]=record["trades"]<100
    return {"research_only":True,"promotion_allowed":False,
        "out_of_sample_certified":False,"trades":total,"mean_net_r":net/total,
        "net_r_total":net,"strategies":strategies,
        "next_action":"expand independent history; inspect regime and costs without tuning on locked OOS"}

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("report");args=p.parse_args()
    print(json.dumps(diagnose(json.loads(Path(args.report).read_text())),indent=2))
