"""Validate offline current exchangeInfo evidence without network access.

Current listings are NOT a historical point-in-time universe and cannot
authorize historical backtests. Supports a manually supplied licensed export.
"""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from signals_v3.discover_current_markets import current_listings

def import_exchange_info(source,destination):
    payload=json.loads(Path(source).read_text())
    markets=current_listings(payload)
    result={"source":"offline_user_supplied_exchangeInfo",
            "imported_at_utc":datetime.now(timezone.utc).isoformat(),
            "current_only":True,"historical_universe_verified":False,
            "price_filter_applied":False,
            "markets":markets}
    out=Path(destination);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2)+"\n")
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("source");p.add_argument("destination")
    a=p.parse_args();r=import_exchange_info(a.source,a.destination)
    print(json.dumps({"markets":len(r["markets"]),"historical_universe_verified":False}))
