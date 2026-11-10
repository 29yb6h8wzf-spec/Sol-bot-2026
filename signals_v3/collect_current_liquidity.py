"""Collect one CURRENT Binance USDT-M research snapshot from public endpoints.

Prospective collection only: never reinterpret this as historical coverage.
No credentials, private endpoints, order endpoints, or deployment.
"""
import json
import time
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path

BASE="https://fapi.binance.com"
def public_json(path,params=None):
    url=BASE+path
    if params:
        url+="?"+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={"User-Agent":"SignalPilot-V3-Research/1.0"})
    try:
        with urllib.request.urlopen(req,timeout=15) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code in (403,451):
            raise RuntimeError('public_market_data_access_blocked_http_'+str(exc.code)) from exc
        raise

def snapshot_symbol(symbol,fetch=public_json,clock_ms=lambda:int(time.time()*1000)):
    if not isinstance(symbol,str) or not symbol.endswith("USDT") or not symbol.isalnum():
        raise ValueError("invalid_symbol")
    start=clock_ms()
    info=fetch("/fapi/v1/exchangeInfo")
    matches=[x for x in info["symbols"] if x["symbol"]==symbol]
    if len(matches)!=1:
        raise ValueError("symbol_not_listed")
    market=matches[0]
    ticker=fetch("/fapi/v1/ticker/24hr",{"symbol":symbol})
    book=fetch("/fapi/v1/depth",{"symbol":symbol,"limit":1000})
    end=clock_ms()
    if end<start or end-start>60_000:
        raise ValueError("snapshot_capture_too_slow")
    price=float(ticker["lastPrice"])
    if price<=0:
        raise ValueError("invalid_last_price")
    if not book.get("bids") or not book.get("asks"):
        raise ValueError("empty_order_book")
    bid=float(book["bids"][0][0]);ask=float(book["asks"][0][0])
    if bid<=0 or ask<=0 or bid>ask:
        raise ValueError("invalid_best_quotes")
    mid=(bid+ask)/2
    lower=mid*(1-0.001);upper=mid*(1+0.001)
    bid_depth=sum(float(p)*float(q) for p,q in book["bids"] if float(p)>=lower)
    ask_depth=sum(float(p)*float(q) for p,q in book["asks"] if float(p)<=upper)
    notional=[float(x.get("notional",x.get("minNotional",0))) for x in market.get("filters",[]) if x.get("filterType") in ("MIN_NOTIONAL","NOTIONAL")]
    if not notional:
        raise ValueError("missing_min_notional")
    return {
        "symbol":symbol,"observed_at_ms":end,"capture_started_at_ms":start,
        "last_price_usd":price,"quote_volume_24h_usd":float(ticker["quoteVolume"]),
        "spread_bps":(ask-bid)/mid*10000,
        "bid_depth_10bps_usd":bid_depth,"ask_depth_10bps_usd":ask_depth,
        "min_notional_usd":max(notional),"status":market["status"],
        "contract_type":market["contractType"],"quote_asset":market["quoteAsset"],
        "current_only":True,"historical_universe_verified":False,
        "depth_limit":1000,"depth_window_bps":10,
        "warning":"Top-1000 depth is a lower bound; not a historical book snapshot",
        "sources":["/fapi/v1/exchangeInfo","/fapi/v1/ticker/24hr","/fapi/v1/depth"]
    }

def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("symbol")
    parser.add_argument("output")
    args=parser.parse_args()
    result=snapshot_symbol(args.symbol)
    path=Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"symbol":args.symbol,"current_only":True,"output":str(path)}))

if __name__=="__main__":
    main()
