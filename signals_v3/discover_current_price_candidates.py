"""Bounded, read-only discovery of CURRENT eligible-priced USDT-M markets.

Price filtering is a discovery prefilter only, not proof of liquidity eligibility.
No historical reconstruction, orders, or deployment.
"""
from math import isfinite
from signals_v3.collect_current_liquidity import public_json, snapshot_symbol
from signals_v3.dynamic_universe import MIN_PRICE_USD, MAX_PRICE_USD

def discover_current_price_candidates(fetch=public_json):
    info=fetch("/fapi/v1/exchangeInfo")
    tickers=fetch("/fapi/v1/ticker/price")
    if not isinstance(info,dict) or not isinstance(info.get("symbols"),list):
        raise ValueError("invalid_exchange_info")
    if not isinstance(tickers,list):
        raise ValueError("invalid_price_tickers")
    prices={}
    for item in tickers:
        try:
            symbol=item["symbol"]
            price=float(item["price"])
        except (KeyError,TypeError,ValueError):
            raise ValueError("invalid_price_ticker")
        if not isfinite(price) or price<=0:
            raise ValueError("invalid_price_ticker")
        if symbol in prices:
            raise ValueError("duplicate_price_ticker")
        prices[symbol]=price
    candidates=[]
    listed=set()
    for market in info["symbols"]:
        if market.get("quoteAsset")!="USDT" or market.get("contractType")!="PERPETUAL" or market.get("status")!="TRADING":
            continue
        symbol=market["symbol"]
        if symbol in listed:
            raise ValueError("duplicate_market_listing")
        listed.add(symbol)
        if symbol not in prices:
            raise ValueError("missing_price_ticker")
        if MIN_PRICE_USD<=prices[symbol]<=MAX_PRICE_USD:
            candidates.append(symbol)
    return tuple(sorted(set(candidates)))

def capture_current_candidates(fetch=public_json,limit=10,clock_ms=None):
    """Explicit small cap to bound public API load; not complete market coverage."""
    if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=20:
        raise ValueError("invalid_capture_limit")
    candidates=discover_current_price_candidates(fetch)
    selected=candidates[:limit]
    snapshots=[]
    for symbol in selected:
        if clock_ms is None:
            snapshots.append(snapshot_symbol(symbol,fetch=fetch))
        else:
            snapshots.append(snapshot_symbol(symbol,fetch=fetch,clock_ms=clock_ms))
    return {"current_only":True,"historical_universe_verified":False,
            "complete_market_capture":len(selected)==len(candidates),
            "candidate_count":len(candidates),"captured_count":len(snapshots),
            "snapshots":snapshots}
