"""Read-only public Binance Futures listing discovery; never submit orders.

This is a CURRENT listing snapshot only, NOT a historical point-in-time universe.
Persist timestamp and raw exchangeInfo metadata for provenance. No credentials.
"""
import json
import urllib.request
from datetime import datetime,timezone
from pathlib import Path

URL="https://fapi.binance.com/fapi/v1/exchangeInfo"

def current_listings(payload):
    if not isinstance(payload,dict) or not isinstance(payload.get("symbols"),list):
        raise ValueError("invalid_exchange_info")
    result=[]
    for s in payload["symbols"]:
        if s.get("quoteAsset")=="USDT" and s.get("contractType")=="PERPETUAL" and s.get("status")=="TRADING":
            result.append({"symbol":s["symbol"],"onboardDate":s.get("onboardDate"),
                           "filters":s.get("filters",[])})
    return sorted(result,key=lambda x:x["symbol"])

def collect(destination):
    request=urllib.request.Request(URL,headers={"User-Agent":"SignalPilot-V3-Research/1.0"})
    with urllib.request.urlopen(request,timeout=15) as response:
        payload=json.load(response)
    snapshot={"source":URL,"captured_at_utc":datetime.now(timezone.utc).isoformat(),
              "current_only":True,"historical_universe_verified":False,
              "price_filter_applied":False,
              "notes":"exchangeInfo does not contain current prices or historical bid/ask depth",
              "markets":current_listings(payload)}
    path=Path(destination);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(snapshot,indent=2)+"\n")
    print(json.dumps({"current_markets":len(snapshot["markets"]),
                      "historical_universe_verified":False,
                      "output":str(path)}))
    return snapshot

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("output")
    args=p.parse_args();collect(args.output)
