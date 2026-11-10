"""Generate an honest archive coverage report from an offline audit JSON.

Does not conflate ZIP integrity with historical market eligibility, and does
not authorize backtesting without point-in-time listings and depth snapshots.
"""
import argparse,json
from collections import Counter,defaultdict
from pathlib import Path

def summarize(audit):
    rows=audit.get("records")
    if not isinstance(rows,list):raise ValueError("missing_audit_records")
    by_symbol=defaultdict(lambda:Counter())
    by_month=defaultdict(lambda:Counter())
    reasons=Counter()
    for row in rows:
        symbol=row["symbol"];month=row["month"]
        state="verified" if row.get("verified") else "blocked"
        by_symbol[symbol][state]+=1;by_month[month][state]+=1
        if state=="blocked":reasons[row.get("reason","unverified")]+=1
    total=len(rows);verified=sum(bool(r.get("verified")) for r in rows)
    return {"total":total,"verified":verified,"blocked":total-verified,
            "coverage_percent":round(100*verified/total,2) if total else 0,
            "by_symbol":{k:dict(v) for k,v in sorted(by_symbol.items())},
            "by_month":{k:dict(v) for k,v in sorted(by_month.items())},
            "blockers":dict(sorted(reasons.items())),
            "historical_universe_verified":False,
            "historical_depth_verified":False,
            "dynamic_backtest_ready":False}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("audit");p.add_argument("--output",required=True)
    a=p.parse_args()
    result=summarize(json.loads(Path(a.audit).read_text()))
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:result[k] for k in ("total","verified","blocked","coverage_percent","dynamic_backtest_ready")}))
