"""Build a deterministic Binance public-data archive acquisition plan.

Produces candidate URLs only. No network, no trading, no historical universe
claims. Each ZIP must be downloaded from an authorized source and verified
before the inventory gate can mark it present.
"""
import argparse
import calendar
import json
from datetime import date
from urllib.parse import quote

BASE="https://data.binance.vision/data/futures/um/monthly"
INTERVALS=("1m","5m","fundingRate")

def months_between(first,last):
    a=date.fromisoformat(first+"-01");b=date.fromisoformat(last+"-01")
    if a>b:raise ValueError("invalid_month_range")
    months=[]
    while a<=b:
        months.append(a.strftime("%Y-%m"))
        a=date(a.year+(a.month==12),a.month%12+1,1)
    return tuple(months)

def archive_url(symbol,month,interval):
    if not symbol.endswith("USDT") or not symbol[:-4].isalnum():
        raise ValueError("invalid_symbol")
    if interval not in INTERVALS:raise ValueError("invalid_interval")
    date.fromisoformat(month+"-01")
    if interval=="fundingRate":
        name=f"{symbol}-fundingRate-{month}.zip"
        return f"{BASE}/fundingRate/{quote(symbol)}/{name}"
    name=f"{symbol}-{interval}-{month}.zip"
    return f"{BASE}/klines/{quote(symbol)}/{interval}/{name}"

def build_plan(symbols,first,last):
    symbols=sorted(set(symbols))
    if not symbols:raise ValueError("empty_symbol_set")
    records=[]
    for month in months_between(first,last):
        for symbol in symbols:
            for interval in INTERVALS:
                records.append({"symbol":symbol,"month":month,"interval":interval,
                                "candidate_url":archive_url(symbol,month,interval),
                                "downloaded":False,"verified":False})
    return {"research_only":True,"no_network_calls":True,
            "historical_universe_verified":False,
            "warning":"Candidate archive URLs are not proof of availability, authenticity, or historic listing.",
            "records":records}

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--symbols",nargs="+",required=True)
    p.add_argument("--first",required=True)
    p.add_argument("--last",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    plan=build_plan(args.symbols,args.first,args.last)
    with open(args.output,"w") as f:json.dump(plan,f,indent=2)
    print(json.dumps({"planned_archives":len(plan["records"]),"downloaded":0,"verified":0}))
