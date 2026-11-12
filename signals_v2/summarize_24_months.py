"""Aggregate immutable monthly research reports without optimizing on evaluation data."""
import argparse,json,math
from pathlib import Path
from collections import defaultdict

def summarize(paths):
    reports=[json.loads(Path(p).read_text()) for p in paths]
    months=[r["month"] for r in reports]
    if len(months)!=len(set(months)):raise ValueError("duplicate_month")
    if not reports:raise ValueError("no_reports")
    for r in reports:
        if not r.get("research_only") or r.get("out_of_sample_certified") is not False:
            raise ValueError("not_exploratory_research")
        if set(r["symbols"])!={"SOLUSDT","XRPUSDT"}:raise ValueError("missing_symbol")
    by_symbol={}
    for symbol in ("SOLUSDT","XRPUSDT"):
        entries=[(r["month"],r["symbols"][symbol]) for r in reports]
        trades=sum(x["trades"] for _,x in entries)
        net=sum(x["net_r_total"] for _,x in entries)
        by_symbol[symbol]={
            "trades":trades,"net_r_total":net,"weighted_mean_net_r":net/trades if trades else None,
            "positive_months":sum(x["mean_net_r"] is not None and x["mean_net_r"]>0 for _,x in entries),
            "negative_months":sum(x["mean_net_r"] is not None and x["mean_net_r"]<0 for _,x in entries),
            "months_with_trades":sum(x["trades"]>0 for _,x in entries),
            "monthly":{m:{"trades":x["trades"],"mean_net_r":x["mean_net_r"]} for m,x in entries}}
    return {"status":"EXPLORATORY_ONLY","months_received":len(reports),"months":sorted(months),
      "oos_certified":False,"profitability_proven":False,"symbols":by_symbol}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("directory");a=p.parse_args()
    paths=sorted(Path(a.directory).rglob("pilot_replay_report.json"))
    if len(paths)!=24:raise SystemExit(f"expected_24_reports_got_{len(paths)}")
    result=summarize(paths)
    Path(a.directory,"24_month_summary.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
