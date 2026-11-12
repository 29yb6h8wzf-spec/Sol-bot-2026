"""Read-only Binance USDT-M archive inventory, not a historical depth reconstruction.

Downloads no data, sends no orders, and never treats today's market listings
as point-in-time historical membership. Use with externally supplied archive
manifest entries to discover missing 1m/5m/funding coverage.
"""
from dataclasses import dataclass
from pathlib import Path
import json

@dataclass(frozen=True)
class ArchiveRecord:
    symbol:str
    month:str
    interval:str
    path:str
    verified:bool

REQUIRED_INTERVALS=("1m","5m","fundingRate")

def inventory(records,months,symbols):
    """Require explicit historical universe snapshots separately before replay."""
    index={}
    for record in records:
        key=(record.symbol,record.month,record.interval)
        if key in index:raise ValueError("duplicate_archive_record:"+str(key))
        index[key]=record
    missing=[];unverified=[]
    for month in months:
        for symbol in symbols:
            for interval in REQUIRED_INTERVALS:
                key=(symbol,month,interval)
                item=index.get(key)
                if item is None:missing.append(key)
                elif not item.verified:unverified.append(key)
    return {"research_only":True,"historical_universe_verified":False,
            "complete_archive_coverage":not missing and not unverified,
            "missing":[list(k) for k in missing],
            "unverified":[list(k) for k in unverified],
            "replay_authorized":False}

def load_manifest(path):
    payload=json.loads(Path(path).read_text())
    if not isinstance(payload,list):raise ValueError("expected_archive_manifest_array")
    return [ArchiveRecord(**row) for row in payload]

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("manifest")
    p.add_argument("--months",nargs="+",required=True)
    p.add_argument("--symbols",nargs="+",required=True)
    args=p.parse_args()
    print(json.dumps(inventory(load_manifest(args.manifest),args.months,args.symbols),indent=2))
