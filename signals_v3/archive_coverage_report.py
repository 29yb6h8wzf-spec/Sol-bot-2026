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


def audit_expected_archive_grid(audit, symbols, months, intervals=("1m","5m","fundingRate")):
    """Fail closed on missing, duplicate or unexpected archive keys.

    This audits the planned OHLCV/funding grid only; it cannot prove historical
    listings, spread or order-book depth and never authorizes a backtest.
    """
    from itertools import product
    rows=audit.get("records")
    if not isinstance(rows,list):
        raise ValueError("missing_audit_records")
    dimensions=(tuple(symbols),tuple(months),tuple(intervals))
    if any(not values or len(set(values))!=len(values) or
           any(not isinstance(v,str) or not v for v in values) for values in dimensions):
        raise ValueError("invalid_expected_archive_grid")
    expected=set(product(*dimensions))
    observed={}
    duplicates=set()
    unexpected=set()
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError("invalid_archive_audit_record")
        key=(row.get("symbol"),row.get("month"),row.get("interval"))
        if key not in expected:
            unexpected.add(key)
            continue
        if key in observed:
            duplicates.add(key)
        observed[key]=row.get("verified") is True
    missing=expected-observed.keys()
    unverified={key for key,verified in observed.items() if not verified}
    complete=not (missing or duplicates or unexpected or unverified)
    return {"expected_count":len(expected),"observed_unique_count":len(observed),
            "verified_unique_count":sum(observed.values()),
            "missing":sorted(missing),"duplicate":sorted(duplicates),
            "unexpected":sorted(unexpected),"unverified":sorted(unverified),
            "archive_grid_complete":complete,
            "historical_universe_verified":False,
            "historical_depth_verified":False,
            "dynamic_backtest_ready":False}
